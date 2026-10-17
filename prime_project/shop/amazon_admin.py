from django.contrib import admin

from .amazon_models import AmazonSource, AmazonSyncRun
from .amazon_forms import AmazonSourceForm


@admin.register(AmazonSource)
class AmazonSourceAdmin(admin.ModelAdmin):
    form = AmazonSourceForm
    list_display = ("asin", "marketplace", "enabled", "publish", "fetched_at", "consecutive_failures", "next_attempt_at")
    list_filter = ("enabled", "publish", "marketplace")
    search_fields = ("asin",)
    fields = ("asin", "marketplace", "enabled", "publish", "product", "fetched_at", "content_expires_at", "offer_expires_at", "next_attempt_at", "consecutive_failures", "last_error", "claimed_at")
    readonly_fields = ("product", "fetched_at", "content_expires_at", "offer_expires_at", "next_attempt_at", "consecutive_failures", "last_error", "claimed_at")

    def get_fields(self, request, obj=None):
        return self.fields if obj else ('product_url',) + self.fields

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("asin", "marketplace") if obj else ())

    def has_delete_permission(self, request, obj=None):
        return False  # Disable the source; preserve its product/favorite identity.


@admin.register(AmazonSyncRun)
class AmazonSyncRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "state", "attempted", "succeeded", "failed", "skipped", "completed_at")
    readonly_fields = tuple(field.name for field in AmazonSyncRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
