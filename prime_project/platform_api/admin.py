from django.contrib import admin
from django import forms
from django_summernote.admin import SummernoteModelAdmin

from .models import BlogPost, SiteSettings


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"
        widgets = {
            "accent_color": forms.TextInput(attrs={"type": "color"}),
            "secondary_accent_color": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    form = SiteSettingsForm
    fieldsets = (
        ("Branding", {"fields": ("name", "accent_color", "secondary_accent_color"), "description": "Save these colors, then refresh the website to see them across V2. Existing artwork and product images keep their original colors."}),
        ("Homepage hero", {"fields": ("hero_title", "hero_subtitle", "hero_image", "hero_button_text", "hero_button_url")}),
        ("Homepage content", {"fields": ("home_sections",)}),
        ("Navigation and footer", {"fields": ("navigation", "footer_text", "social_links", "buy_me_a_coffee_url")}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BlogPost)
class BlogPostAdmin(SummernoteModelAdmin):
    change_list_template = "admin/platform_api/blog_posts.html"
    list_display = ("title", "category", "status", "published_at", "author")
    list_filter = ("status", "category")
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    summernote_fields = ("body",)
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


from . import youtube_admin  # noqa: E402,F401
