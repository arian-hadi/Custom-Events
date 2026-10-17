"""Hosted Checkout: the signed webhook, never a browser redirect, records payment."""
import logging
import uuid
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from urllib.parse import urlsplit

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import PaymentOrder, ProductPayment, StripeWebhookReceipt

logger = logging.getLogger(__name__)
EVENT_TYPES = {"checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.async_payment_failed", "checkout.session.expired"}
ZERO_DECIMAL = {"bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "vnd", "vuv", "xaf", "xof", "xpf"}
THREE_DECIMAL = {"bhd", "jod", "kwd", "omr", "tnd"}


class CheckoutUnavailable(ValueError):
    pass


class CheckoutConflict(ValueError):
    def __init__(self, message, *, code="checkout_conflict", order_id=None):
        super().__init__(message)
        self.code = code
        self.order_id = str(order_id) if order_id else None


def display_amount(amount, currency):
    places = 0 if currency in ZERO_DECIMAL else 3 if currency in THREE_DECIMAL else 2
    return f"{Decimal(amount) / (10 ** places):.{places}f}"


def stripe_mode():
    key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if key.startswith(("sk_test_", "rk_test_")):
        return False
    if key.startswith(("sk_live_", "rk_live_")) and getattr(settings, "STRIPE_ALLOW_LIVE_PAYMENTS", False):
        if getattr(settings, "V2_LOCAL_PREVIEW", False):
            raise CheckoutUnavailable("Local previews only support Stripe test keys.")
        return True
    raise CheckoutUnavailable("Stripe test credentials are not configured, or live payments have not been enabled.")


def stripe_client():
    stripe_mode()
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=1, http_client=stripe.RequestsClient(timeout=15))


def checkout_origin():
    origin = getattr(settings, "STRIPE_CHECKOUT_BASE_URL", "").rstrip("/")
    try:
        parsed = urlsplit(origin)
        parsed.port
    except ValueError as exc:
        raise CheckoutUnavailable("Configure a valid Stripe checkout website origin.") from exc
    local = parsed.hostname in {"localhost", "127.0.0.1"} and not stripe_mode()
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and local)) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise CheckoutUnavailable("Configure STRIPE_CHECKOUT_BASE_URL as the public HTTPS website origin.")
    return origin


def checkout_ready():
    if not getattr(settings, "STRIPE_CHECKOUT_ENABLED", False) or not getattr(settings, "STRIPE_WEBHOOK_SECRET", "").startswith("whsec_"):
        return False
    try:
        stripe_mode()
        checkout_origin()
    except CheckoutUnavailable:
        return False
    return True


def external_product(product):
    return product.category != "transformers_2_0" or product.ecommerce_platform != "none" or hasattr(product, "amazon_source")


def checkout_product_data(product):
    try:
        config = product.payment_config
    except ProductPayment.DoesNotExist:
        return {"configured": False, "enabled": False}
    available = config.enabled and product.is_active and not product.is_free() and not external_product(product)
    return {
        "configured": bool(available),
        "enabled": bool(available and checkout_ready()),
        "amount_minor": config.amount_minor, "currency": config.currency,
        "display_amount": display_amount(config.amount_minor, config.currency),
        "fulfillment_kind": config.fulfillment_kind, "fulfillment_note": config.fulfillment_note,
    }


def order_data(order):
    return {
        "id": str(order.pk), "product_id": order.product_id, "product_name": order.product_name,
        "amount_minor": order.amount_minor, "currency": order.currency,
        "display_amount": display_amount(order.amount_minor, order.currency), "status": order.status,
        "fulfillment_status": order.fulfillment_status, "fulfillment_kind": order.fulfillment_kind,
        "fulfillment_note": order.fulfillment_note, "created_at": order.created_at, "paid_at": order.paid_at,
    }


def _object_id(value):
    return value.get("id") if isinstance(value, dict) or hasattr(value, "get") else value


def verified_price(client, config):
    price = client.v1.prices.retrieve(config.stripe_price_id, {"expand": ["product"]})
    product = price.get("product")
    if (
        price.get("id") != config.stripe_price_id or not price.get("active")
        or price.get("livemode") is not stripe_mode() or price.get("type") != "one_time"
        or price.get("billing_scheme") != "per_unit" or price.get("recurring")
        or price.get("custom_unit_amount") or price.get("transform_quantity")
        or price.get("currency") != config.currency or price.get("unit_amount") != config.amount_minor
        or not hasattr(product, "get") or not product.get("active") or not product.get("id")
    ):
        raise CheckoutConflict("The configured price is unavailable or differs from Stripe. Please contact the shop.")
    return price


def _checkout_parameters(order, user_email, config):
    origin = checkout_origin()
    params = {
        "mode": "payment", "ui_mode": "hosted",
        "line_items": [{"price": order.stripe_price_id, "quantity": 1}],
        "client_reference_id": str(order.pk),
        "metadata": {"order_id": str(order.pk), "user_id": str(order.user_id), "product_id": str(order.product_id)},
        "customer_email": user_email,
        "success_url": f"{origin}/account/orders/{order.pk}?checkout=success",
        "cancel_url": f"{origin}/account/orders/{order.pk}?checkout=cancelled",
        "allow_promotion_codes": False, "automatic_tax": {"enabled": False},
        "adaptive_pricing": {"enabled": False},
        "expires_at": int((timezone.now() + timedelta(hours=1)).timestamp()),
    }
    if config.fulfillment_kind == "physical_manual":
        params["shipping_address_collection"] = {"allowed_countries": config.shipping_countries}
    return params


def create_checkout(user, product, idempotency_key):
    if not checkout_ready():
        raise CheckoutUnavailable("Checkout is not configured yet.")
    if external_product(product) or not product.is_active or product.is_free():
        raise CheckoutConflict("This product is not available for Stripe checkout.")
    existing = PaymentOrder.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        if existing.product_id != product.pk:
            raise CheckoutConflict("This request key belongs to a different purchase.")
        return resume_checkout(existing)
    try:
        config = product.payment_config
    except ProductPayment.DoesNotExist as exc:
        raise CheckoutUnavailable("This product does not have a Stripe price configured.") from exc
    if not config.enabled:
        raise CheckoutUnavailable("Checkout for this product is disabled.")
    try:
        config.full_clean()
    except ValidationError as exc:
        raise CheckoutUnavailable("This product's checkout configuration needs staff review.") from exc
    price = verified_price(stripe_client(), config)
    with transaction.atomic():
        # Lock configuration so an admin's simultaneous edit cannot change the quoted price.
        current = ProductPayment.objects.select_for_update().get(pk=config.pk)
        if (current.updated_at != config.updated_at or not current.enabled):
            raise CheckoutConflict("The price was updated. Refresh the product before trying again.")
        order, created = PaymentOrder.objects.get_or_create(user=user, idempotency_key=idempotency_key, defaults={
            "product": product, "product_name": product.name,
            "stripe_price_id": config.stripe_price_id, "stripe_product_id": _object_id(price["product"]),
            "currency": config.currency, "amount_minor": config.amount_minor, "livemode": stripe_mode(),
            "fulfillment_kind": config.fulfillment_kind, "fulfillment_note": config.fulfillment_note,
        })
        if order.product_id != product.pk:
            raise CheckoutConflict("This request key belongs to a different purchase.")
        if created:
            order.checkout_parameters = _checkout_parameters(order, user.email, config)
            order.save(update_fields=["checkout_parameters", "updated_at"])
    return resume_checkout(order)


def resume_checkout(order):
    if order.livemode is not stripe_mode():
        raise CheckoutConflict("This purchase belongs to a different payment environment.")
    if order.status not in {"creating", "pending"}:
        return order, None
    if order.expires_at and order.expires_at <= timezone.now():
        return order, None
    if order.stripe_session_id:
        return order, order.checkout_url or None
    if timezone.now() >= order.created_at + timedelta(minutes=25):
        # A new Stripe Session needs >=30 minutes until expiry. Never revive stale parameters
        # or reuse the Stripe key beyond its retention window after an uncertain request.
        raise CheckoutConflict(
            "This checkout request can no longer be retried safely. Review your existing order or contact the shop before starting another purchase.",
            code="expired_request", order_id=order.pk,
        )
    session = stripe_client().v1.checkout.sessions.create(order.checkout_parameters, {"idempotency_key": f"shop-order-{order.pk}"})
    if not session.get("id") or not session.get("url") or urlsplit(session["url"]).scheme != "https" or urlsplit(session["url"]).hostname != "checkout.stripe.com":
        raise CheckoutUnavailable("Stripe did not return a valid hosted checkout session.")
    with transaction.atomic():
        current = PaymentOrder.objects.select_for_update().get(pk=order.pk)
        if current.stripe_session_id and current.stripe_session_id != session["id"]:
            raise CheckoutConflict("Checkout session mismatch. Contact the shop.")
        current.stripe_session_id = session["id"]
        current.checkout_url = session["url"]
        current.expires_at = datetime.fromtimestamp(session["expires_at"], datetime_timezone.utc)
        if current.status == "creating":
            current.status = "pending"
        current.save(update_fields=["stripe_session_id", "checkout_url", "expires_at", "status", "updated_at"])
    return current, current.checkout_url if current.status == "pending" else None


def _session_mismatch(order, session, lines):
    metadata = session.get("metadata") or {}
    expected = {"order_id": str(order.pk), "user_id": str(order.user_id), "product_id": str(order.product_id)}
    if any(metadata.get(key) != value for key, value in expected.items()) or session.get("client_reference_id") != str(order.pk):
        return "Checkout ownership metadata did not match the order."
    if order.stripe_session_id and session.get("id") != order.stripe_session_id:
        return "Checkout session did not match the order."
    if session.get("livemode") is not order.livemode or session.get("mode") != "payment":
        return "Checkout mode did not match the order."
    if session.get("currency") != order.currency or session.get("amount_subtotal") != order.amount_minor or session.get("amount_total") != order.amount_minor:
        return "Checkout amount or currency did not match the order."
    rows = lines.get("data") or []
    if lines.get("has_more") or len(rows) != 1:
        return "Checkout contained unexpected line items."
    item = rows[0]
    price = item.get("price") or {}
    if (item.get("quantity") != 1 or price.get("id") != order.stripe_price_id
        or _object_id(price.get("product")) != order.stripe_product_id
        or item.get("currency") != order.currency or item.get("amount_total") != order.amount_minor
        or price.get("unit_amount") != order.amount_minor or price.get("currency") != order.currency):
        return "Checkout item or price did not match the order."
    return None


def process_webhook(event):
    """Persist one receipt and state transition atomically. Stripe retries transient failures."""
    if event.get("account") or event.get("context"):
        raise CheckoutConflict("Connected-account and organization events are not supported.")
    if event.get("livemode") is not stripe_mode():
        raise CheckoutConflict("Webhook belongs to a different payment environment.")
    event_id, event_type = event.get("id"), event.get("type")
    if not isinstance(event_id, str) or not event_id.startswith("evt_") or len(event_id) > 100:
        raise CheckoutConflict("Invalid event identifier.")
    if StripeWebhookReceipt.objects.filter(event_id=event_id).exists():
        return "duplicate"
    if event_type not in EVENT_TYPES:
        return "ignored"
    signed_session = event.get("data", {}).get("object", {})
    session_id = signed_session.get("id")
    if not isinstance(session_id, str) or not session_id.startswith("cs_"):
        raise CheckoutConflict("Invalid checkout event.")
    try:
        order_id = uuid.UUID((signed_session.get("metadata") or {}).get("order_id", ""))
    except (ValueError, TypeError, AttributeError):
        return "unrelated"
    order = PaymentOrder.objects.filter(pk=order_id).first()
    if not order:
        return "unrelated"
    # Retrieve through this account's secret key; do not trust a browser-supplied session or amount.
    client = stripe_client()
    session = client.v1.checkout.sessions.retrieve(session_id)
    lines = client.v1.checkout.sessions.line_items.list(session_id, {"limit": 2})
    with transaction.atomic():
        order = PaymentOrder.objects.select_for_update().get(pk=order.pk)
        receipt, created = StripeWebhookReceipt.objects.get_or_create(event_id=event_id, defaults={"event_type": event_type, "order": order, "outcome": "processing"})
        if not created:
            return "duplicate"
        mismatch = _session_mismatch(order, session, lines)
        if mismatch:
            order.review_reason = mismatch
            if order.status != "paid":
                order.status = "review_required"
            receipt.outcome = "review_required"
            logger.error("Stripe checkout verification failed for order %s: %s", order.pk, mismatch)
        else:
            order.stripe_session_id = session_id
            if session.get("payment_status") == "paid" and session.get("status") == "complete":
                intent = _object_id(session.get("payment_intent"))
                if not isinstance(intent, str) or not intent.startswith("pi_"):
                    raise CheckoutConflict("Paid checkout has no payment intent.")
                order.stripe_payment_intent_id = intent
                if order.status != "paid":
                    order.status = "paid"
                    order.paid_at = timezone.now()
                    order.fulfillment_status = "awaiting_fulfillment"
                receipt.outcome = "paid"
            elif order.status not in {"paid", "failed", "expired", "review_required"}:
                if session.get("status") == "expired":
                    order.status = "expired"
                elif event_type == "checkout.session.async_payment_failed":
                    order.status = "failed"
                else:
                    order.status = "pending"
                receipt.outcome = order.status
            else:
                receipt.outcome = f"already_{order.status}"
        order.save()
        receipt.save(update_fields=["outcome"])
    return receipt.outcome
