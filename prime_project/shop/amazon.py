"""Bounded, retryable refresh of curated Amazon products, with expiring content."""
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .amazon_models import AmazonSource, AmazonSyncRun
from .amazon_provider import AmazonConfigurationError, AmazonError, CreatorsClient


AFFILIATE_DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."
CONTENT_DISCLOSURE = "CERTAIN CONTENT THAT APPEARS ON THIS SITE COMES FROM AMAZON. THIS CONTENT IS PROVIDED ‘AS IS’ AND IS SUBJECT TO CHANGE OR REMOVAL AT ANY TIME."
PRICE_DISCLAIMER = "Product prices and availability are accurate as of the date/time indicated and are subject to change. Any price and availability information displayed on Amazon at the time of purchase will apply to the purchase of this product."


def purge_expired(*, now=None):
    """Drop provider content; do not keep a historical copy in product/run records."""
    now = now or timezone.now()
    offers = AmazonSource.objects.filter(offer_expires_at__lte=now).update(
        price=None, currency="", display_price="", availability="", offer_expires_at=None,
    )
    content = AmazonSource.objects.filter(content_expires_at__lte=now).update(
        title="", image_url="", detail_url="", content_expires_at=None,
    )
    return {"offers": offers, "content": content}


def catalog_queryset(queryset, *, now=None):
    now = now or timezone.now()
    normal = Q(amazon_source__isnull=True, is_active=True)
    automated = Q(amazon_source__enabled=True, amazon_source__publish=True, amazon_source__content_expires_at__gt=now)
    if not getattr(settings, "AMAZON_AUTOMATION_ENABLED", False):
        automated = Q(pk__in=[])
    return queryset.filter(normal | automated).select_related("amazon_source")


def product_overlay(product, *, now=None):
    """Merge this into V2 product JSON after the ordinary product serializer."""
    try:
        source = product.amazon_source
    except AmazonSource.DoesNotExist:
        return None
    now = now or timezone.now()
    fresh = bool(source.content_expires_at and source.content_expires_at > now)
    offer_fresh = bool(fresh and source.offer_expires_at and source.offer_expires_at > now)
    price = str(source.price) if offer_fresh and source.price is not None else None
    return {
        "name": source.title if fresh else f"Amazon item {source.asin}", "description": "",
        "thumbnail": source.image_url if fresh else "", "main_image": source.image_url if fresh else "",
        "images": [source.image_url] if fresh and source.image_url else [],
        "original_price": price, "current_price": price, "display_price": source.display_price if price is not None else "",
        "currency": source.currency if price is not None else "", "price_available": price is not None,
        "price_updated_at": source.fetched_at if offer_fresh else None,
        # Clients can expire already-rendered content using a server-relative
        # clock even when the tab stays open or its local clock is incorrect.
        "amazon_offer_expires_at": source.offer_expires_at,
        "amazon_content_expires_at": source.content_expires_at,
        "amazon_observed_at": now,
        "affiliate_disclosure": AFFILIATE_DISCLOSURE, "content_disclosure": CONTENT_DISCLOSURE,
        "price_disclaimer": PRICE_DISCLAIMER, "amazon_automated": True,
        "redirect_url": source.detail_url if fresh else "", "ecommerce_platform": "amazon",
        "is_free": False, "discount_percentage": "0", "free_deadline": None, "video_url": None,
        "checkout_enabled": False,
    }


def claim_source(source_id, *, force=False, now=None):
    now = now or timezone.now()
    token = uuid.uuid4()
    candidates = AmazonSource.objects.filter(pk=source_id, enabled=True).filter(
        Q(claim_token__isnull=True) | Q(claimed_at__lt=now - timedelta(minutes=15))
    )
    if not force:
        candidates = candidates.filter(next_attempt_at__lte=now)
    if candidates.update(claim_token=token, claimed_at=now):
        return token
    return None


def _store_result(source_id, token, data, *, now):
    from .models import Product
    with transaction.atomic():
        source = AmazonSource.objects.select_for_update().get(pk=source_id)
        if source.claim_token != token or not source.enabled:
            return False
        if source.product_id is None:
            # These deliberately inactive identity records support favorites/URLs only.
            # Provider content stays in expiring AmazonSource, never legacy templates.
            product = Product(
                name=f"Amazon item {source.asin}", description="Amazon affiliate product",
                category="merges_1_0", thumbnail="", main_image="", original_price=0,
                redirect_url=f"https://{source.marketplace}/dp/{source.asin}",
                ecommerce_platform="amazon", is_active=False,
            )
            # Bulk insert bypasses Product's upload-only form validation; this record
            # cannot enter the legacy catalog and is serialized only through overlay.
            Product.objects.bulk_create([product])
            source.product_id = product.pk
        minutes = min(60, max(1, int(getattr(settings, "AMAZON_REFRESH_MINUTES", 45))))
        values = dict(data)
        offer_valid_until = values.pop("offer_valid_until", None)
        offer_expiry = min(now + timedelta(hours=1), offer_valid_until) if offer_valid_until else now + timedelta(hours=1)
        AmazonSource.objects.filter(pk=source.pk, claim_token=token).update(
            **values, product_id=source.product_id, fetched_at=now,
            content_expires_at=now + timedelta(hours=24), offer_expires_at=offer_expiry,
            next_attempt_at=now + timedelta(minutes=minutes), consecutive_failures=0,
            last_error="", claim_token=None, claimed_at=None,
        )
        return True


def _store_error(source_id, token, message, *, now):
    with transaction.atomic():
        source = AmazonSource.objects.select_for_update().get(pk=source_id)
        if source.claim_token != token:
            return
        failures = source.consecutive_failures + 1
        delay = min(360, 5 * 2 ** min(failures - 1, 7))
        AmazonSource.objects.filter(pk=source.pk, claim_token=token).update(
            consecutive_failures=failures, last_error=message[:250],
            next_attempt_at=now + timedelta(minutes=delay), claim_token=None, claimed_at=None,
        )


def sync_sources(*, limit=25, force=False, dry_run=False, source_ids=None):
    if not 1 <= limit <= 100:
        raise AmazonError("The synchronization limit must be between 1 and 100.")
    queryset = AmazonSource.objects.filter(enabled=True).order_by("next_attempt_at", "pk")
    if source_ids is not None:
        queryset = queryset.filter(pk__in=source_ids)
    if not force:
        queryset = queryset.filter(next_attempt_at__lte=timezone.now())
    ids = list(queryset.values_list("pk", flat=True)[:limit])
    # A dry run is an offline plan: no API calls, writes, purge or credential use.
    if dry_run:
        return {"dry_run": True, "source_ids": ids, "attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    purge_expired()
    if not getattr(settings, "AMAZON_AUTOMATION_ENABLED", False):
        raise AmazonConfigurationError("Amazon automation is disabled. Configure credentials and enable it when ready.")
    now = timezone.now()
    AmazonSyncRun.objects.filter(state="running", heartbeat_at__lt=now - timedelta(minutes=15)).update(
        state="failed", completed_at=now, error="Interrupted worker; abandoned source claims can now be retried.",
    )
    try:
        with transaction.atomic():
            run = AmazonSyncRun.objects.create()
    except IntegrityError:
        return {"state": "busy", "attempted": 0, "succeeded": 0, "failed": 0, "skipped": len(ids)}
    try:
        client = CreatorsClient()
    except AmazonConfigurationError as exc:
        run.state, run.error, run.completed_at = "failed", str(exc), timezone.now()
        run.save(update_fields=["state", "error", "completed_at"])
        raise
    for index, source_id in enumerate(ids):
        token = claim_source(source_id, force=force)
        if token is None:
            run.skipped += 1
            continue
        if index:
            time.sleep(1.1)  # Single worker below 1 request/sec; source claims prevent overlaps.
        run.attempted += 1
        try:
            source = AmazonSource.objects.get(pk=source_id)
            data = client.get_item(source.asin, source.marketplace)
            if _store_result(source_id, token, data, now=timezone.now()):
                run.succeeded += 1
            else:
                run.skipped += 1
                AmazonSource.objects.filter(pk=source_id, claim_token=token).update(claim_token=None, claimed_at=None)
        except Exception as exc:
            # Provider bodies/exception repr can contain secrets. Persist safe errors only.
            message = str(exc) if isinstance(exc, AmazonError) else "Amazon synchronization failed unexpectedly; retry after reviewing server configuration."
            _store_error(source_id, token, message, now=timezone.now())
            run.failed += 1
        run.heartbeat_at = timezone.now()
        run.save(update_fields=["attempted", "succeeded", "failed", "skipped", "heartbeat_at"])
    run.state = "partial" if run.failed else "complete"
    run.completed_at = timezone.now()
    run.save(update_fields=["state", "completed_at", "attempted", "succeeded", "failed", "skipped"])
    return {"run_id": run.pk, "state": run.state, "attempted": run.attempted, "succeeded": run.succeeded, "failed": run.failed, "skipped": run.skipped}
