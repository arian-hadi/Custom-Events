import logging
import uuid

import stripe
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.api_views import limited
from platform_api.views import endpoint, payload
from .models import PaymentOrder, Product
from .payments import CheckoutConflict, CheckoutUnavailable, create_checkout, order_data, process_webhook

logger = logging.getLogger(__name__)


@endpoint(("POST",), authenticated=True)
def checkout(request):
    if limited(request, "stripe-checkout", limit=20, period=600, identity=str(request.user.pk)):
        return JsonResponse({"error": "Too many checkout attempts. Please try again later."}, status=429)
    data = payload(request)
    product_id = data.get("product_id")
    if type(product_id) is not int or not 1 <= product_id < 2 ** 63 or set(data) - {"product_id", "idempotency_key"}:
        return JsonResponse({"error": "Provide a product_id and a unique idempotency_key only."}, status=400)
    try:
        key = uuid.UUID(data.get("idempotency_key", ""))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Provide a UUID idempotency_key; reuse it when retrying the same purchase."}, status=400)
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    try:
        order, url = create_checkout(request.user, product, key)
    except CheckoutUnavailable as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except CheckoutConflict as exc:
        return JsonResponse({"error": str(exc), "code": exc.code, "order_id": exc.order_id}, status=409)
    except stripe.StripeError:
        logger.warning("Stripe checkout request failed; account %s", request.user.pk)
        return JsonResponse({"error": "The payment provider is temporarily unavailable. Retry this purchase with the same request key."}, status=503)
    return JsonResponse({"order": order_data(order), "checkout_url": url})


@endpoint(authenticated=True)
def orders(request):
    records = PaymentOrder.objects.filter(user=request.user).order_by("-created_at")[:100]
    return JsonResponse({"orders": [order_data(order) for order in records]})


@endpoint(authenticated=True)
def order_detail(request, order_id):
    order = get_object_or_404(PaymentOrder, pk=order_id, user=request.user)
    return JsonResponse({"order": order_data(order)})


@csrf_exempt
@never_cache
@require_POST
def stripe_webhook(request):
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not secret.startswith("whsec_"):
        return JsonResponse({"error": "Webhook is not configured."}, status=503)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({"error": "Webhook payload too large."}, status=400)
    try:
        event = stripe.Webhook.construct_event(request.body, request.headers.get("Stripe-Signature", ""), secret)
    except (ValueError, stripe.SignatureVerificationError):
        return JsonResponse({"error": "Invalid webhook signature or payload."}, status=400)
    try:
        result = process_webhook(event)
    except CheckoutConflict as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except CheckoutUnavailable:
        return JsonResponse({"error": "Payment credentials are unavailable."}, status=503)
    except Exception:
        # Do not log payment payloads, personal details, secrets or raw provider errors.
        logger.error("Stripe webhook processing failed; delivery will be retried.")
        return JsonResponse({"error": "Unable to process this event yet."}, status=503)
    return JsonResponse({"received": True, "result": result})
