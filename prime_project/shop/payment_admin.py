from django import forms
from django.contrib import admin
from django.utils.html import format_html
from .models import PaymentOrder, ProductPayment, StripeWebhookReceipt


@admin.register(ProductPayment)
class ProductPaymentAdmin(admin.ModelAdmin):
    list_display = ("product", "enabled", "stripe_price_id", "amount_minor", "currency", "fulfillment_kind")
    list_filter = ("enabled", "currency", "fulfillment_kind")
    search_fields = ("product__name", "stripe_price_id")
    autocomplete_fields = ("product",)
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Hosted Stripe checkout", {"fields": ("product", "enabled", "stripe_price_id", "currency", "amount_minor"), "description": "Use a fixed one-time Stripe Price. The server verifies its exact amount and currency before checkout. External affiliate products keep their external purchase links."}),
        ("Delivery arrangements", {"fields": ("fulfillment_kind", "fulfillment_note", "shipping_countries"), "description": "Staff must deliver paid orders. This integration does not send downloads or purchase shipping labels. Include any shipping and tax in the configured price; automatic tax, shipping charges and discounts are disabled."}),
        ("Record", {"fields": ("updated_at",)}),
    )


class PaymentOrderForm(forms.ModelForm):
    class Meta:
        model = PaymentOrder
        fields = "__all__"

    def clean(self):
        data = super().clean()
        fulfillment = data.get("fulfillment_status")
        if self.instance.status != "paid" and fulfillment != "awaiting_payment":
            raise forms.ValidationError("Only webhook-confirmed paid orders can be fulfilled.")
        if self.instance.status == "paid" and fulfillment == "awaiting_payment":
            raise forms.ValidationError("A paid order must remain in a fulfillment state.")
        return data


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    form = PaymentOrderForm
    list_display = ("id", "product_name", "user", "amount_minor", "currency", "status", "fulfillment_status", "created_at")
    list_filter = ("status", "fulfillment_status", "livemode", "currency")
    search_fields = ("id", "product_name", "user__email", "stripe_session_id", "stripe_payment_intent_id")
    list_select_related = ("user", "product")
    readonly_fields = tuple(field.name for field in PaymentOrder._meta.fields if field.name not in {"fulfillment_status", "fulfillment_admin_note"}) + ("stripe_dashboard",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Payment in Stripe")
    def stripe_dashboard(self, obj):
        if not obj.stripe_payment_intent_id:
            return "Awaiting a verified payment. Review events in Stripe Workbench if necessary."
        mode = "" if obj.livemode else "test/"
        return format_html('<a href="https://dashboard.stripe.com/{}payments/{}" target="_blank" rel="noopener noreferrer">Open payment and delivery details</a>', mode, obj.stripe_payment_intent_id)


@admin.register(StripeWebhookReceipt)
class StripeWebhookReceiptAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "order", "outcome", "received_at")
    list_filter = ("outcome", "event_type")
    search_fields = ("event_id", "order__id")
    readonly_fields = tuple(field.name for field in StripeWebhookReceipt._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
