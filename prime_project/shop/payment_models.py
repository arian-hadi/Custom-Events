"""Opt-in Stripe products and an auditable, server-owned payment ledger."""
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class ProductPayment(models.Model):
    product = models.OneToOneField("shop.Product", on_delete=models.CASCADE, related_name="payment_config")
    enabled = models.BooleanField(default=False)
    stripe_price_id = models.CharField(max_length=100, help_text="The one-time Price ID from your Stripe account (price_...).")
    currency = models.CharField(max_length=3, default="usd")
    amount_minor = models.PositiveBigIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99999999)], help_text="Exact Stripe minor-unit amount, e.g. 1299 for USD 12.99 or 1299 for JPY 1299.")
    fulfillment_kind = models.CharField(max_length=24, choices=[("digital_manual", "Digital delivery by staff"), ("physical_manual", "Shipping by staff")], default="digital_manual")
    fulfillment_note = models.TextField(help_text="Shown before payment and on the order. Explain what is delivered, how and when, and included shipping/tax where relevant.")
    shipping_countries = models.JSONField(default=list, blank=True, help_text='Physical orders only: allowed destination codes, e.g. ["US", "GB"]. Shipping must be included in the fixed price.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stripe product configuration"

    def clean(self):
        super().clean()
        if not re.fullmatch(r"price_[A-Za-z0-9]+", self.stripe_price_id or ""):
            raise ValidationError({"stripe_price_id": "Enter a Stripe Price ID."})
        if not re.fullmatch(r"[a-z]{3}", self.currency or ""):
            raise ValidationError({"currency": "Use a lowercase three-letter currency code."})
        if self.currency in {"isk", "ugx"} and self.amount_minor and self.amount_minor % 100:
            raise ValidationError({"amount_minor": "Stripe requires multiples of 100 for this currency."})
        if not isinstance(self.shipping_countries, list) or any(not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}", code) for code in self.shipping_countries):
            raise ValidationError({"shipping_countries": "Enter a list of uppercase two-letter country codes."})
        if self.fulfillment_kind == "physical_manual" and not self.shipping_countries:
            raise ValidationError({"shipping_countries": "Physical orders need at least one shipping destination."})
        if not (self.fulfillment_note or "").strip():
            raise ValidationError({"fulfillment_note": "Explain the delivery arrangements before enabling payment."})
        if self.product_id and (self.product.category != "transformers_2_0" or self.product.ecommerce_platform != "none" or hasattr(self.product, "amazon_source")):
            raise ValidationError("External affiliate products cannot use Stripe checkout.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} ({self.stripe_price_id})"


class PaymentOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_orders")
    product = models.ForeignKey("shop.Product", on_delete=models.PROTECT, related_name="payment_orders")
    idempotency_key = models.UUIDField()
    product_name = models.CharField(max_length=200)
    stripe_price_id = models.CharField(max_length=100)
    stripe_product_id = models.CharField(max_length=100)
    currency = models.CharField(max_length=3)
    amount_minor = models.PositiveBigIntegerField()
    livemode = models.BooleanField(default=False)
    fulfillment_kind = models.CharField(max_length=24)
    fulfillment_note = models.TextField()
    status = models.CharField(max_length=24, default="creating", choices=[("creating", "Creating checkout"), ("pending", "Awaiting payment"), ("paid", "Paid"), ("failed", "Payment failed"), ("expired", "Checkout expired"), ("review_required", "Staff review required")])
    fulfillment_status = models.CharField(max_length=24, default="awaiting_payment", choices=[("awaiting_payment", "Awaiting payment"), ("awaiting_fulfillment", "Awaiting staff fulfillment"), ("fulfilled", "Fulfilled by staff")])
    fulfillment_admin_note = models.TextField(blank=True, help_text="Internal delivery/tracking notes. Not included in the member API.")
    stripe_session_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    checkout_url = models.URLField(max_length=2000, blank=True)
    checkout_parameters = models.JSONField(default=dict, editable=False)
    review_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("user", "idempotency_key"), name="shop_order_user_request_unique")]

    def __str__(self):
        return f"{self.id} — {self.product_name} — {self.status}"


class StripeWebhookReceipt(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    order = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT, related_name="webhook_receipts", null=True, blank=True)
    outcome = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.event_id}: {self.outcome}"
