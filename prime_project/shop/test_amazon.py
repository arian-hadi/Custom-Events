import io
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .amazon import catalog_queryset, claim_source, product_overlay, purge_expired, sync_sources
from .amazon_models import AmazonSource, AmazonSyncRun
from .amazon_provider import API_URL, AmazonConfigurationError, AmazonError, CreatorsClient, parse_item
from .models import Product


ASIN = "B0199980K4"


def response_fixture():
    return {"itemResults": {"items": [{
        "asin": ASIN, "detailPageURL": f"https://www.amazon.com/dp/{ASIN}?tag=example-20&linkCode=ogi",
        "itemInfo": {"title": {"displayValue": "Example figure"}},
        "images": {"primary": {"large": {"url": "https://m.media-amazon.com/images/I/example.jpg"}}},
        "offersV2": {"listings": [{"isBuyBoxWinner": True, "violatesMAP": False,
            "availability": {"type": "IN_STOCK"},
            "price": {"money": {"amount": 59.49, "currency": "USD", "displayAmount": "$59.49"}},
        }]},
    }]}}


PROVIDER_SETTINGS = {
    "AMAZON_AUTOMATION_ENABLED": True, "AMAZON_CREATORS_CLIENT_ID": "test-id",
    "AMAZON_CREATORS_CLIENT_SECRET": "test-secret", "AMAZON_PARTNER_TAG": "example-20",
    "AMAZON_MARKETPLACE": "www.amazon.com", "AMAZON_CREATORS_CREDENTIAL_VERSION": "3.1",
}


@override_settings(**PROVIDER_SETTINGS)
class AmazonProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_documented_camelcase_response_and_offersv2_money(self):
        data = parse_item(response_fixture(), ASIN, "www.amazon.com")
        self.assertEqual(data["price"], Decimal("59.49"))
        self.assertIn("?tag=example-20&linkCode=ogi", data["detail_url"])
        variant = response_fixture()
        variant["itemsResult"] = variant.pop("itemResults")
        self.assertEqual(parse_item(variant, ASIN, "www.amazon.com"), data)

    def test_missing_asin_does_not_import_other_item(self):
        with self.assertRaises(AmazonError):
            parse_item(response_fixture(), "B000000000", "www.amazon.com")

    def test_unsafe_urls_and_invalid_money_rejected(self):
        for link in ("http://www.amazon.com/x", "https://www.amazon.com.evil.test/x", "https://user@www.amazon.com/x", "https://127.0.0.1/x", "javascript:alert(1)", "https://www.amazon.com:444/x", "https://www.amazon.com/dp/B000000000", "https://www.amazon.com/gp/redirect.html?url=https://evil.test"):
            with self.subTest(link=link):
                payload = response_fixture()
                payload["itemResults"]["items"][0]["detailPageURL"] = link
                with self.assertRaises(AmazonError):
                    parse_item(payload, ASIN, "www.amazon.com")
        for amount in ("NaN", "Infinity", "-1", "1.234", "9999999999999"):
            with self.subTest(amount=amount):
                payload = response_fixture()
                payload["itemResults"]["items"][0]["offersV2"]["listings"][0]["price"]["money"]["amount"] = amount
                with self.assertRaises(AmazonError):
                    parse_item(payload, ASIN, "www.amazon.com")

    def test_untrusted_remote_image_rejected(self):
        payload = response_fixture()
        payload["itemResults"]["items"][0]["images"]["primary"]["large"]["url"] = "https://attacker.test/track"
        with self.assertRaises(AmazonError):
            parse_item(payload, ASIN, "www.amazon.com")

    def test_no_offer_restricted_or_map_offer_never_becomes_zero(self):
        for change in ({"violatesMAP": True}, {"dealDetails": {"accessType": "PRIME_EXCLUSIVE"}}, {"availability": {"type": "OUTOFSTOCK"}}, {"isBuyBoxWinner": False}, {"type": "SUBSCRIBE_AND_SAVE"}):
            payload = response_fixture()
            payload["itemResults"]["items"][0]["offersV2"]["listings"][0].update(change)
            self.assertIsNone(parse_item(payload, ASIN, "www.amazon.com")["price"])

    def test_documented_null_optional_objects_remain_a_valid_item(self):
        payload = response_fixture()
        item = payload["itemResults"]["items"][0]
        item["images"]["primary"].update({"large": None, "medium": None, "small": {"url": "https://m.media-amazon.com/images/I/small.jpg"}})
        item["offersV2"] = None
        data = parse_item(payload, ASIN, "www.amazon.com")
        self.assertIsNone(data["price"])
        self.assertTrue(data["image_url"].endswith("small.jpg"))

    def test_expired_or_future_deal_price_hidden(self):
        for deal in ({"endTime": (timezone.now() - timedelta(hours=1)).isoformat()}, {"startTime": (timezone.now() + timedelta(hours=1)).isoformat()}):
            payload = response_fixture()
            payload["itemResults"]["items"][0]["offersV2"]["listings"][0]["dealDetails"] = deal
            self.assertIsNone(parse_item(payload, ASIN, "www.amazon.com")["price"])

    def test_oauth_region_and_getitems_request_and_cached_token(self):
        with override_settings(AMAZON_CREATORS_CREDENTIAL_VERSION="3.2"):
            client = CreatorsClient()
        with patch.object(client, "_post", side_effect=[{"access_token": "token", "expires_in": 3600}, response_fixture(), response_fixture()]) as post:
            client.get_item(ASIN, "www.amazon.com")
            client.get_item(ASIN, "www.amazon.com")
        self.assertEqual(post.call_count, 3)
        token_call, api_call = post.call_args_list[:2]
        self.assertEqual(token_call.args[0], "https://api.amazon.co.uk/auth/o2/token")
        self.assertEqual(token_call.args[1]["scope"], "creatorsapi::default")
        self.assertEqual(api_call.args[0], API_URL)
        self.assertEqual(api_call.args[1]["itemIds"], [ASIN])
        self.assertEqual(api_call.args[2]["Authorization"], "Bearer token")
        self.assertEqual(api_call.args[2]["x-marketplace"], "www.amazon.com")

    def test_http_errors_do_not_leak_secrets_or_follow_redirects(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 403
        response.text = "secret-provider-body"
        with patch("shop.amazon_provider.requests.post", return_value=response) as post:
            with self.assertRaises(AmazonError) as captured:
                CreatorsClient().token()
        self.assertNotIn("secret-provider-body", str(captured.exception))
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_response_size_bounded_and_json_validated(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.iter_content.return_value = [b" " * 40961]
        with patch("shop.amazon_provider.requests.post", return_value=response):
            with self.assertRaises(AmazonError):
                CreatorsClient().token()

    def test_requires_new_credentials_and_valid_marketplace(self):
        with override_settings(AMAZON_CREATORS_CLIENT_SECRET=""):
            with self.assertRaises(AmazonConfigurationError):
                CreatorsClient()
        with self.assertRaises(AmazonConfigurationError):
            CreatorsClient().get_item(ASIN, "www.amazon.co.uk")


@override_settings(**PROVIDER_SETTINGS)
class AmazonAutomationTests(TestCase):
    def setUp(self):
        self.source = AmazonSource.objects.create(asin=ASIN, publish=True)
        self.data = parse_item(response_fixture(), ASIN, "www.amazon.com")

    def sync(self, **kwargs):
        with patch("shop.amazon.CreatorsClient") as client:
            client.return_value.get_item.return_value = self.data
            return sync_sources(**kwargs)

    def test_idempotent_refresh_creates_inactive_shell_and_fresh_catalog(self):
        result = self.sync()
        self.assertEqual(result["succeeded"], 1)
        self.source.refresh_from_db()
        product = self.source.product
        self.assertFalse(product.is_active)
        self.assertEqual(product.name, f"Amazon item {ASIN}")
        self.assertFalse(product.thumbnail)
        self.assertEqual(catalog_queryset(Product.objects.all()).get().pk, product.pk)
        payload = product_overlay(product)
        self.assertEqual(payload["current_price"], "59.49")
        self.assertFalse(payload["is_free"])
        self.assertFalse(payload["checkout_enabled"])
        self.assertIn("qualifying purchases", payload["affiliate_disclosure"])
        self.assertEqual(payload["amazon_offer_expires_at"], self.source.offer_expires_at)
        self.assertEqual(payload["amazon_content_expires_at"], self.source.content_expires_at)
        self.assertLess(payload["amazon_observed_at"], payload["amazon_offer_expires_at"])
        self.assertEqual(self.sync()["attempted"], 0)
        self.assertEqual(self.sync(force=True)["succeeded"], 1)
        self.assertEqual(Product.objects.count(), 1)

    def test_offer_expiry_hides_price_content_expiry_hides_product(self):
        self.sync()
        self.source.refresh_from_db()
        product = Product.objects.select_related("amazon_source").get()
        after_offer = timezone.now() + timedelta(hours=2)
        self.assertIsNone(product_overlay(product, now=after_offer)["current_price"])
        self.assertFalse(product_overlay(product, now=after_offer)["is_free"])
        expired_offer = product_overlay(product, now=after_offer)
        self.assertEqual(expired_offer["amazon_observed_at"], after_offer)
        self.assertLessEqual(expired_offer["amazon_offer_expires_at"], expired_offer["amazon_observed_at"])
        self.assertEqual(catalog_queryset(Product.objects.all(), now=after_offer).count(), 1)
        after_content = timezone.now() + timedelta(hours=25)
        self.assertEqual(catalog_queryset(Product.objects.all(), now=after_content).count(), 0)
        purge_expired(now=after_content)
        self.source.refresh_from_db()
        self.assertEqual(self.source.title, "")
        self.assertEqual(self.source.image_url, "")
        self.assertEqual(self.source.detail_url, "")
        self.assertIsNone(self.source.price)

    def test_public_api_exposes_server_relative_expiry_and_purged_offer_is_null(self):
        self.sync()
        self.source.refresh_from_db()
        url = f'/api/v2/products/{self.source.product_id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        product = response.json()['product']
        observed = parse_datetime(product['amazon_observed_at'])
        offer_expiry = parse_datetime(product['amazon_offer_expires_at'])
        content_expiry = parse_datetime(product['amazon_content_expires_at'])
        self.assertTrue(timezone.is_aware(observed))
        self.assertLess(observed, offer_expiry)
        self.assertLess(offer_expiry, content_expiry)
        AmazonSource.objects.filter(pk=self.source.pk).update(offer_expires_at=timezone.now()-timedelta(seconds=1))
        purge_expired()
        product = self.client.get(url).json()['product']
        self.assertIsNone(product['amazon_offer_expires_at'])
        self.assertIsNone(product['current_price'])
        self.assertIsNotNone(product['amazon_content_expires_at'])
        self.assertIsNotNone(product['amazon_observed_at'])

    def test_disabled_and_unpublished_not_visible(self):
        self.sync()
        with override_settings(AMAZON_AUTOMATION_ENABLED=False):
            self.assertFalse(catalog_queryset(Product.objects.all()).exists())
        AmazonSource.objects.filter(pk=self.source.pk).update(publish=False)
        self.assertFalse(catalog_queryset(Product.objects.all()).exists())

    def test_dry_run_offline_no_mutation_even_when_disabled(self):
        with override_settings(AMAZON_AUTOMATION_ENABLED=False), patch("shop.amazon.CreatorsClient") as client:
            before = AmazonSource.objects.values().get()
            result = sync_sources(dry_run=True)
            client.assert_not_called()
        self.assertEqual(result["source_ids"], [self.source.pk])
        self.assertEqual(AmazonSource.objects.values().get(), before)
        self.assertEqual(AmazonSyncRun.objects.count(), 0)

    def test_failure_records_backoff_without_partial_product_or_secret(self):
        with patch("shop.amazon.CreatorsClient") as client:
            client.return_value.get_item.side_effect = RuntimeError("token=secret")
            result = sync_sources()
        self.assertEqual(result["failed"], 1)
        self.source.refresh_from_db()
        self.assertIsNone(self.source.product_id)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(self.source.consecutive_failures, 1)
        self.assertGreater(self.source.next_attempt_at, timezone.now())
        self.assertNotIn("secret", self.source.last_error)
        self.assertIsNone(self.source.claim_token)

    def test_atomic_rollback_on_database_write_failure(self):
        from .amazon import _store_result
        token = claim_source(self.source.pk)
        with patch("shop.amazon.AmazonSource.objects.filter", side_effect=RuntimeError("write failure")):
            with self.assertRaises(RuntimeError):
                _store_result(self.source.pk, token, self.data, now=timezone.now())
        self.assertFalse(Product.objects.exists())
        self.source.refresh_from_db()
        self.assertIsNone(self.source.product_id)

    def test_claim_prevents_concurrent_duplicate_and_recovers_abandoned_claim(self):
        first = claim_source(self.source.pk)
        self.assertIsNotNone(first)
        self.assertIsNone(claim_source(self.source.pk, force=True))
        AmazonSource.objects.filter(pk=self.source.pk).update(claimed_at=timezone.now() - timedelta(minutes=16))
        self.assertNotEqual(claim_source(self.source.pk), first)

    def test_only_one_worker_runs_and_abandoned_run_recovers(self):
        active = AmazonSyncRun.objects.create()
        with patch("shop.amazon.CreatorsClient") as provider:
            self.assertEqual(sync_sources()["state"], "busy")
            provider.assert_not_called()
        AmazonSyncRun.objects.filter(pk=active.pk).update(heartbeat_at=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.sync()["succeeded"], 1)
        active.refresh_from_db()
        self.assertEqual(active.state, "failed")

    def test_source_identity_validation_and_manual_products_preserved(self):
        with self.assertRaises(ValidationError):
            AmazonSource.objects.create(asin="bad")
        self.source.asin = "B000000000"
        with self.assertRaises(ValidationError):
            self.source.save()
        product = Product(name="Handmade item", description="Keep this", original_price=15, redirect_url="https://example.com", thumbnail="", main_image="")
        Product.objects.bulk_create([product])
        self.sync()
        product.refresh_from_db()
        self.assertEqual(product.description, "Keep this")
        self.assertEqual(product.original_price, 15)
        self.assertIn(product.pk, catalog_queryset(Product.objects.all()).values_list("pk", flat=True))

    def test_automated_shell_cannot_be_activated_or_edited_through_model(self):
        self.sync()
        self.source.refresh_from_db()
        product = self.source.product
        product.is_active = True
        with self.assertRaises(ValidationError):
            product.save()
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_command_dry_run_and_purge_only(self):
        out = io.StringIO()
        call_command("sync_amazon_products", "--dry-run", stdout=out)
        self.assertTrue(json.loads(out.getvalue())["dry_run"])
        with override_settings(AMAZON_AUTOMATION_ENABLED=False):
            call_command("sync_amazon_products", "--purge-only", stdout=io.StringIO())

    def test_v2_catalog_detail_search_and_favorites_use_fresh_overlay(self):
        self.sync()
        self.source.refresh_from_db()
        member = get_user_model().objects.create_user(email="amazon-member@example.test", username="amazon-member", password="Testing-Password-123", is_verified=True)
        self.client.force_login(member)
        product_id = self.source.product_id
        listing = self.client.get("/api/v2/products/?search=Example").json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["results"][0]["name"], "Example figure")
        detail = self.client.get(f"/api/v2/products/{product_id}/").json()["product"]
        self.assertEqual(detail["current_price"], "59.49")
        self.assertFalse(detail["is_free"])
        self.assertTrue(detail["amazon_automated"])
        response = self.client.post(f"/api/v2/products/{product_id}/favorite/", {"is_favorite": True}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/v2/favorites/").json()["count"], 1)
        AmazonSource.objects.filter(pk=self.source.pk).update(offer_expires_at=timezone.now() - timedelta(seconds=1))
        detail = self.client.get(f"/api/v2/products/{product_id}/").json()["product"]
        self.assertIsNone(detail["current_price"])
        self.assertFalse(detail["price_available"])
        self.assertFalse(detail["is_free"])
        AmazonSource.objects.filter(pk=self.source.pk).update(content_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"/api/v2/products/{product_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v2/products/").json()["count"], 0)
        self.assertEqual(self.client.get("/api/v2/favorites/").json()["count"], 0)
