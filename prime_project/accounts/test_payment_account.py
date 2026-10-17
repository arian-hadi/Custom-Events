import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from shop.models import PaymentOrder, Product


class PaymentAccountDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.buyer = User.objects.create_user(email="buyer-delete@example.test", username="buyer-delete", password="Testing-Password-123", is_verified=True)
        cls.unrelated = User.objects.create_user(email="other-delete@example.test", username="other-delete", password="Testing-Password-123", is_verified=True)
        cls.product = Product(name="Paid pack", description="Digital material", thumbnail="shop/test.png", main_image="shop/test.png", original_price="12.99", redirect_url="https://example.test/buy")
        Product.objects.bulk_create([cls.product])
        cls.order = PaymentOrder.objects.create(
            user=cls.buyer, product=cls.product, idempotency_key=uuid.uuid4(),
            product_name=cls.product.name, stripe_price_id="price_test", stripe_product_id="prod_test",
            currency="usd", amount_minor=1299, fulfillment_kind="digital_manual", fulfillment_note="Manual delivery.",
        )

    def test_order_records_block_deletion_gracefully_and_keep_session(self):
        self.client.force_login(self.buyer)
        for status in ("creating", "pending", "paid", "failed", "expired", "review_required"):
            with self.subTest(status=status):
                PaymentOrder.objects.filter(pk=self.order.pk).update(status=status)
                response = self.client.post(reverse("profile"), {"action": "delete_account"})
                self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
                message = " ".join(str(item) for item in get_messages(response.wsgi_request))
                self.assertIn("Your account is still active", message)
                self.assertIn(f'href="{reverse("contact")}"', message)
                self.assertTrue(get_user_model().objects.filter(pk=self.buyer.pk, is_active=True).exists())
                self.assertEqual(self.client.session.get("_auth_user_id"), str(self.buyer.pk))
                self.assertEqual(PaymentOrder.objects.get(pk=self.order.pk).status, status)

    def test_other_members_without_protected_records_can_still_delete_their_account(self):
        self.client.force_login(self.unrelated)
        response = self.client.post(reverse("profile"), {"action": "delete_account"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(get_user_model().objects.filter(pk=self.unrelated.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(get_user_model().objects.filter(pk=self.buyer.pk).exists())
        self.assertTrue(PaymentOrder.objects.filter(pk=self.order.pk).exists())

    def test_delete_account_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        self.assertEqual(client.post(reverse("profile"), {"action": "delete_account"}).status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.buyer.pk).exists())

    def test_anonymous_delete_cannot_remove_any_member(self):
        response = self.client.post(reverse("profile"), {"action": "delete_account"})
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertTrue(get_user_model().objects.filter(pk=self.buyer.pk).exists())
