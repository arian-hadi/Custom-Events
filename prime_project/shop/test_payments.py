import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import stripe
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import PaymentOrder, Product, ProductPayment, StripeWebhookReceipt
from .payment_admin import PaymentOrderForm
from .payments import checkout_product_data, display_amount


@override_settings(STRIPE_CHECKOUT_ENABLED=True, STRIPE_SECRET_KEY="sk_test_fixture", STRIPE_WEBHOOK_SECRET="whsec_fixture", STRIPE_ALLOW_LIVE_PAYMENTS=False, STRIPE_CHECKOUT_BASE_URL="https://website.example.test")
class StripeCheckoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email="buyer@example.test", username="buyer", password="Testing-Password-123", is_verified=True)
        cls.other = User.objects.create_user(email="other-buyer@example.test", username="other-buyer", password="Testing-Password-123", is_verified=True)
        cls.product = Product(name="Editor pack", description="Digital editing materials", thumbnail="shop/test.png", main_image="shop/test.png", original_price="99.00", redirect_url="https://example.test/legacy")
        Product.objects.bulk_create([cls.product])
        cls.config = ProductPayment.objects.create(product=cls.product, enabled=True, stripe_price_id="price_fixture", currency="usd", amount_minor=1299, fulfillment_note="Staff email the files within two working days; total includes applicable tax.")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.member)
        self.provider = MagicMock()
        self.provider.v1.prices.retrieve.return_value = {
            "id": "price_fixture", "active": True, "livemode": False, "type": "one_time", "billing_scheme": "per_unit",
            "recurring": None, "currency": "usd", "unit_amount": 1299, "product": {"id": "prod_fixture", "active": True},
        }
        self.provider.v1.checkout.sessions.create.side_effect = self.provider_session
        self.provider.v1.checkout.sessions.retrieve.side_effect = lambda *args: copy.deepcopy(self.session)
        self.provider.v1.checkout.sessions.line_items.list.side_effect = lambda *args: copy.deepcopy(self.lines)
        self.mock_client = patch("shop.payments.stripe_client", return_value=self.provider)
        self.mock_client.start()
        self.addCleanup(self.mock_client.stop)
        self.lines = {"has_more": False, "data": [{"quantity": 1, "currency": "usd", "amount_total": 1299, "price": {"id": "price_fixture", "product": "prod_fixture", "unit_amount": 1299, "currency": "usd"}}]}

    def provider_session(self, params, options):
        self.session = {
            "id": "cs_test_fixture", "url": "https://checkout.stripe.com/c/pay/cs_test_fixture",
            "expires_at": params["expires_at"], "metadata": params["metadata"], "client_reference_id": params["client_reference_id"],
            "mode": "payment", "livemode": False, "currency": "usd", "amount_total": 1299, "amount_subtotal": 1299,
            "payment_status": "unpaid", "status": "open", "payment_intent": None,
        }
        return copy.deepcopy(self.session)

    def start_checkout(self, key=None, **extra):
        return self.client.post("/api/v2/payments/checkout/", {"product_id": self.product.pk, "idempotency_key": str(key or uuid.uuid4()), **extra}, content_type="application/json")

    def event(self, event_type="checkout.session.completed", event_id="evt_fixture", **extra):
        return {"id": event_id, "object": "event", "type": event_type, "livemode": False, "data": {"object": copy.deepcopy(self.session)}, **extra}

    def post_event(self, event=None, signature=True):
        raw = json.dumps(event or self.event()).encode()
        stamp = int(time.time())
        digest = hmac.new(b"whsec_fixture", f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
        header = f"t={stamp},v1={digest}" if signature else "t=1,v1=invalid"
        return Client(enforce_csrf_checks=True).post("/api/v2/payments/stripe/webhook/", raw, content_type="application/json", HTTP_STRIPE_SIGNATURE=header)

    def pay(self):
        self.session.update(payment_status="paid", status="complete", payment_intent="pi_fixture")

    def test_checkout_uses_verified_server_price_and_stable_order_metadata(self):
        response = self.start_checkout()
        self.assertEqual(response.status_code, 200, response.content)
        order = PaymentOrder.objects.get()
        params, options = self.provider.v1.checkout.sessions.create.call_args.args
        self.assertEqual(order.amount_minor, 1299)
        self.assertEqual(params["line_items"], [{"price": "price_fixture", "quantity": 1}])
        self.assertEqual(params["metadata"]["user_id"], str(self.member.pk))
        self.assertEqual(params["success_url"], f"https://website.example.test/account/orders/{order.pk}?checkout=success")
        self.assertEqual(options["idempotency_key"], f"shop-order-{order.pk}")
        self.assertEqual(response.json()["order"]["display_amount"], "12.99")
        self.assertNotIn("checkout_parameters", response.json()["order"])

    def test_repeated_request_reuses_one_order_and_one_session(self):
        key = uuid.uuid4()
        first = self.start_checkout(key)
        second = self.start_checkout(key)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(PaymentOrder.objects.count(), 1)
        self.assertEqual(self.provider.v1.checkout.sessions.create.call_count, 1)

    def test_network_failure_retries_same_stripe_idempotency_key(self):
        key = uuid.uuid4()
        calls = []
        def uncertain_create(params, options):
            calls.append((copy.deepcopy(params), copy.deepcopy(options)))
            if len(calls) == 1:
                raise stripe.APIConnectionError("simulated timeout")
            return self.provider_session(params, options)
        self.provider.v1.checkout.sessions.create.side_effect = uncertain_create
        self.assertEqual(self.start_checkout(key).status_code, 503)
        self.assertEqual(self.start_checkout(key).status_code, 200)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(PaymentOrder.objects.count(), 1)

    def test_browser_cannot_supply_amount_currency_redirect_or_price(self):
        for field, value in (("amount", 1), ("currency", "eur"), ("success_url", "https://evil.test"), ("price_id", "price_cheaper")):
            self.assertEqual(self.start_checkout(**{field: value}).status_code, 400)
        self.provider.v1.checkout.sessions.create.assert_not_called()

    def test_invalid_idempotency_key_is_rejected(self):
        self.assertEqual(self.start_checkout("wrong").status_code, 400)

    def test_invalid_product_identifiers_are_rejected_without_database_overflow(self):
        for value in (True, -1, 2 ** 100, "1"):
            self.assertEqual(self.start_checkout(product_id=value).status_code, 400)

    def test_disabled_checkout_and_live_key_fail_closed(self):
        with self.settings(STRIPE_CHECKOUT_ENABLED=False):
            self.assertEqual(self.start_checkout().status_code, 503)
        with self.settings(STRIPE_SECRET_KEY="sk_live_fixture"):
            self.assertEqual(self.start_checkout().status_code, 503)
        with self.settings(STRIPE_SECRET_KEY="sk_live_fixture", STRIPE_ALLOW_LIVE_PAYMENTS=True, V2_LOCAL_PREVIEW=True):
            self.assertEqual(self.start_checkout().status_code, 503)
        self.assertFalse(PaymentOrder.objects.exists())

    def test_external_affiliate_and_free_products_cannot_be_charged(self):
        Product.objects.filter(pk=self.product.pk).update(category="merges_1_0", ecommerce_platform="amazon")
        self.assertEqual(self.start_checkout().status_code, 409)
        Product.objects.filter(pk=self.product.pk).update(category="transformers_2_0", ecommerce_platform="none", free_deadline_active=True, free_deadline=timezone.now() + timedelta(days=1))
        self.assertEqual(self.start_checkout().status_code, 409)
        self.assertFalse(PaymentOrder.objects.exists())

    def test_inactive_or_unverified_members_cannot_checkout(self):
        self.member.is_verified = False
        self.member.save(update_fields=["is_verified"])
        self.assertEqual(self.start_checkout().status_code, 401)
        self.member.is_verified, self.member.is_active = True, False
        self.member.save(update_fields=["is_verified", "is_active"])
        self.assertEqual(self.start_checkout().status_code, 401)

    def test_checkout_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        self.assertEqual(client.post("/api/v2/payments/checkout/", {"product_id": self.product.pk, "idempotency_key": str(uuid.uuid4())}, content_type="application/json").status_code, 403)

    def test_mismatched_recurring_or_inactive_stripe_price_never_creates_order(self):
        original = self.provider.v1.prices.retrieve.return_value.copy()
        for overrides in ({"unit_amount": 1}, {"currency": "eur"}, {"type": "recurring"}, {"active": False}, {"livemode": True}, {"transform_quantity": {"divide_by": 10}}, {"product": {"id": "prod_fixture", "active": False}}):
            self.provider.v1.prices.retrieve.return_value = {**original, **overrides}
            self.assertEqual(self.start_checkout().status_code, 409)
        self.assertFalse(PaymentOrder.objects.exists())

    def test_unsigned_or_tampered_webhook_cannot_change_order(self):
        self.start_checkout()
        self.pay()
        self.assertEqual(self.post_event(signature=False).status_code, 400)
        self.assertEqual(PaymentOrder.objects.get().status, "pending")
        self.provider.v1.checkout.sessions.retrieve.assert_not_called()

    def test_signed_paid_webhook_is_idempotent_and_preserves_fulfillment(self):
        self.start_checkout()
        self.pay()
        self.assertEqual(self.post_event().status_code, 200)
        order = PaymentOrder.objects.get()
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.fulfillment_status, "awaiting_fulfillment")
        paid_at = order.paid_at
        order.fulfillment_status = "fulfilled"
        order.save(update_fields=["fulfillment_status"])
        self.assertEqual(self.post_event().json()["result"], "duplicate")
        self.assertEqual(self.post_event(self.event(event_id="evt_second")).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.paid_at, paid_at)
        self.assertEqual(order.fulfillment_status, "fulfilled")
        self.assertEqual(StripeWebhookReceipt.objects.count(), 2)

    def test_success_redirect_and_session_completed_unpaid_are_not_payment(self):
        self.start_checkout()
        order = PaymentOrder.objects.get()
        self.assertEqual(self.client.get(f"/api/v2/payments/orders/{order.pk}/?checkout=success").json()["order"]["status"], "pending")
        self.session["status"] = "complete"
        self.assertEqual(self.post_event().status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")
        self.assertIsNone(order.paid_at)
        self.pay()
        self.assertEqual(self.post_event(self.event("checkout.session.async_payment_succeeded", "evt_async")).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")

    def test_async_failure_preserves_nonpayment_even_after_late_events(self):
        self.start_checkout()
        self.session["status"] = "complete"
        self.assertEqual(self.post_event(self.event("checkout.session.async_payment_failed")).status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "failed")
        self.session["status"] = "expired"
        self.assertEqual(self.post_event(self.event("checkout.session.expired", "evt_expired")).status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "failed")
        self.assertIsNone(PaymentOrder.objects.get().paid_at)

    def test_expired_checkout_does_not_reopen_on_late_completed_event(self):
        self.start_checkout()
        self.session["status"] = "expired"
        self.assertEqual(self.post_event(self.event("checkout.session.expired")).status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "expired")
        self.session["status"] = "complete"
        self.assertEqual(self.post_event(self.event(event_id="evt_late_unpaid")).status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "expired")

    def test_late_failure_event_never_downgrades_paid_order(self):
        self.start_checkout()
        self.pay()
        self.post_event()
        self.session.update(payment_status="unpaid", status="complete")
        self.assertEqual(self.post_event(self.event("checkout.session.async_payment_failed", "evt_late")).status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "paid")

    def test_wrong_amount_or_price_needs_review_not_fulfillment(self):
        self.start_checkout()
        self.pay()
        self.session["amount_total"] = 1
        self.assertEqual(self.post_event().json()["result"], "review_required")
        self.assertEqual(PaymentOrder.objects.get().status, "review_required")
        self.assertIsNone(PaymentOrder.objects.get().paid_at)
        self.session["amount_total"] = 1299
        self.lines["data"][0]["price"]["id"] = "price_wrong"
        self.assertEqual(self.post_event(self.event(event_id="evt_wrong_item")).json()["result"], "review_required")
        self.assertIsNone(PaymentOrder.objects.get().paid_at)

    def test_wrong_owner_metadata_needs_review(self):
        self.start_checkout()
        self.pay()
        self.session["metadata"]["user_id"] = str(self.other.pk)
        self.assertEqual(self.post_event().json()["result"], "review_required")
        self.assertIsNone(PaymentOrder.objects.get().paid_at)

    def test_connected_account_and_wrong_environment_rejected(self):
        self.start_checkout()
        self.pay()
        self.assertEqual(self.post_event(self.event(account="acct_other")).status_code, 400)
        self.assertEqual(self.post_event(self.event(livemode=True)).status_code, 400)
        self.assertIsNone(PaymentOrder.objects.get().paid_at)

    def test_webhook_provider_outage_rolls_back_receipt_for_retry(self):
        self.start_checkout()
        self.pay()
        self.provider.v1.checkout.sessions.retrieve.side_effect = stripe.APIConnectionError("temporary")
        self.assertEqual(self.post_event().status_code, 503)
        self.assertFalse(StripeWebhookReceipt.objects.exists())
        self.provider.v1.checkout.sessions.retrieve.side_effect = lambda *args: copy.deepcopy(self.session)
        self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "paid")

    def test_order_history_is_private_and_does_not_fetch_or_infer_payment(self):
        self.start_checkout()
        order = PaymentOrder.objects.get()
        self.assertEqual(len(self.client.get("/api/v2/payments/orders/").json()["orders"]), 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/api/v2/payments/orders/{order.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v2/payments/orders/").json()["orders"], [])
        self.provider.v1.checkout.sessions.retrieve.assert_not_called()

    def test_zero_and_three_decimal_prices_and_readiness_serializer(self):
        self.assertEqual(display_amount(1299, "usd"), "12.99")
        self.assertEqual(display_amount(1299, "jpy"), "1299")
        self.assertEqual(display_amount(1299, "kwd"), "1.299")
        self.assertEqual(display_amount(500, "isk"), "5.00")
        data = checkout_product_data(Product.objects.get(pk=self.product.pk))
        self.assertTrue(data["enabled"])
        self.assertEqual(data["display_amount"], "12.99")
        with self.settings(STRIPE_CHECKOUT_ENABLED=False):
            self.assertFalse(checkout_product_data(Product.objects.get(pk=self.product.pk))["enabled"])
        Product.objects.filter(pk=self.product.pk).update(free_deadline_active=True, free_deadline=timezone.now() + timedelta(days=1))
        self.assertFalse(checkout_product_data(Product.objects.get(pk=self.product.pk))["configured"])

    def test_physical_orders_require_destinations_and_collect_shipping(self):
        self.config.fulfillment_kind = "physical_manual"
        with self.assertRaises(ValidationError):
            self.config.save()
        self.config.shipping_countries = ["US", "GB"]
        self.config.save()
        self.assertEqual(self.start_checkout().status_code, 200)
        params = self.provider.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params["shipping_address_collection"], {"allowed_countries": ["US", "GB"]})

    def test_admin_cannot_mark_unpaid_order_as_fulfilled(self):
        self.start_checkout()
        form = PaymentOrderForm(instance=PaymentOrder.objects.get(), data={"fulfillment_status": "fulfilled"})
        self.assertFalse(form.is_valid())
        self.assertIn("Only webhook-confirmed paid orders", str(form.errors))

    def test_webhook_still_records_existing_payment_when_checkout_disabled(self):
        self.start_checkout()
        self.pay()
        with self.settings(STRIPE_CHECKOUT_ENABLED=False):
            self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(PaymentOrder.objects.get().status, "paid")

    def test_unrelated_signed_event_does_not_change_order(self):
        self.start_checkout()
        self.session["metadata"]["order_id"] = str(uuid.uuid4())
        self.assertEqual(self.post_event().json()["result"], "unrelated")
        self.assertEqual(PaymentOrder.objects.get().status, "pending")
        self.provider.v1.checkout.sessions.retrieve.assert_not_called()

    def test_webhook_validates_currency_and_exact_item_count(self):
        self.start_checkout()
        self.pay()
        self.session["currency"] = "eur"
        self.assertEqual(self.post_event().json()["result"], "review_required")
        self.session["currency"] = "usd"
        self.lines["data"].append(copy.deepcopy(self.lines["data"][0]))
        self.assertEqual(self.post_event(self.event(event_id="evt_extra_items")).json()["result"], "review_required")
        self.assertIsNone(PaymentOrder.objects.get().paid_at)

    def test_missing_webhook_key_and_invalid_redirect_origin_disable_checkout(self):
        with self.settings(STRIPE_WEBHOOK_SECRET=""):
            self.assertEqual(self.start_checkout().status_code, 503)
        for origin in ("https://example.test/path", "http://example.test", "https://user:password@example.test", "https://example.test:invalid"):
            with self.settings(STRIPE_CHECKOUT_BASE_URL=origin):
                self.assertEqual(self.start_checkout().status_code, 503)
        self.assertFalse(PaymentOrder.objects.exists())

    def test_http_localhost_allowed_only_for_test_payments(self):
        with self.settings(STRIPE_CHECKOUT_BASE_URL="http://localhost:5173"):
            self.assertEqual(self.start_checkout().status_code, 200)
        with self.settings(STRIPE_SECRET_KEY="sk_live_fixture", STRIPE_ALLOW_LIVE_PAYMENTS=True, STRIPE_CHECKOUT_BASE_URL="http://localhost:5173"):
            self.assertEqual(self.start_checkout().status_code, 503)

    def test_price_change_after_network_failure_preserves_original_retry_parameters(self):
        key = uuid.uuid4()
        self.provider.v1.checkout.sessions.create.side_effect = stripe.APIConnectionError("simulated timeout")
        self.assertEqual(self.start_checkout(key).status_code, 503)
        original = copy.deepcopy(PaymentOrder.objects.get().checkout_parameters)
        ProductPayment.objects.filter(pk=self.config.pk).update(amount_minor=1999, stripe_price_id="price_changed")
        self.provider.v1.checkout.sessions.create.side_effect = self.provider_session
        self.assertEqual(self.start_checkout(key).status_code, 200)
        self.assertEqual(self.provider.v1.checkout.sessions.create.call_args.args[0], original)
        self.assertEqual(PaymentOrder.objects.get().amount_minor, 1299)

    def test_expired_uncertain_request_returns_recovery_code_without_new_session(self):
        key = uuid.uuid4()
        self.provider.v1.checkout.sessions.create.side_effect = stripe.APIConnectionError("simulated timeout")
        self.assertEqual(self.start_checkout(key).status_code, 503)
        order = PaymentOrder.objects.get()
        PaymentOrder.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=26))
        response = self.start_checkout(key)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "expired_request")
        self.assertEqual(response.json()["order_id"], str(order.pk))
        self.assertEqual(self.provider.v1.checkout.sessions.create.call_count, 1)
        self.assertEqual(PaymentOrder.objects.count(), 1)
        self.assertEqual(PaymentOrder.objects.get().status, "creating")

    def test_amazon_linked_product_cannot_checkout_even_if_legacy_category_unchanged(self):
        from .models import AmazonSource
        source = AmazonSource.objects.create(asin="B000000001", marketplace="www.amazon.com")
        AmazonSource.objects.filter(pk=source.pk).update(product=self.product)
        self.assertEqual(self.start_checkout().status_code, 409)
        self.assertFalse(PaymentOrder.objects.exists())
