"""Curated Amazon sources; provider content is separate from handmade products."""
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


MARKETPLACES = (
    "www.amazon.com", "www.amazon.ca", "www.amazon.com.mx", "www.amazon.com.br",
    "www.amazon.co.uk", "www.amazon.de", "www.amazon.fr", "www.amazon.it", "www.amazon.es",
    "www.amazon.nl", "www.amazon.com.be", "www.amazon.eg", "www.amazon.in", "www.amazon.ie",
    "www.amazon.pl", "www.amazon.sa", "www.amazon.se", "www.amazon.com.tr", "www.amazon.ae",
    "www.amazon.co.jp", "www.amazon.sg", "www.amazon.com.au",
)


class AmazonSource(models.Model):
    asin = models.CharField(max_length=10)
    marketplace = models.CharField(max_length=40, default="www.amazon.com", choices=[(x, x) for x in MARKETPLACES])
    enabled = models.BooleanField(default=True)
    publish = models.BooleanField(default=False, help_text="Show fresh provider content in the V2 catalog after review.")
    product = models.OneToOneField("shop.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="amazon_source")
    title = models.CharField(max_length=500, blank=True)
    image_url = models.URLField(max_length=1500, blank=True)
    detail_url = models.URLField(max_length=2000, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    display_price = models.CharField(max_length=100, blank=True)
    availability = models.CharField(max_length=80, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    content_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=250, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("marketplace", "asin"), name="amazon_unique_marketplace_asin")]
        ordering = ("marketplace", "asin")

    def clean(self):
        super().clean()
        self.asin = self.asin.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{10}", self.asin):
            raise ValidationError({"asin": "Use a ten-character Amazon ASIN."})
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            if (original.asin, original.marketplace, original.product_id) != (self.asin, self.marketplace, self.product_id):
                raise ValidationError("An existing source's ASIN, marketplace and product link cannot be changed.")
        elif self.product_id:
            raise ValidationError("Products are linked by synchronization; existing handmade products cannot be imported.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.marketplace}: {self.asin}"


class AmazonSyncRun(models.Model):
    started_at = models.DateTimeField(default=timezone.now)
    heartbeat_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=20, default="running", choices=[(v, v) for v in ("running", "complete", "partial", "failed")])
    attempted = models.PositiveIntegerField(default=0)
    succeeded = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("-started_at",)
        constraints = [models.UniqueConstraint(fields=("state",), condition=models.Q(state="running"), name="amazon_one_running_sync")]
