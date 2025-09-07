# announcements/admin.py

from django.contrib import admin
from .models import Announcement
from .forms import AnnouncementAdminForm
from django.utils.html import format_html

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    form = AnnouncementAdminForm
    list_display = ('title', 'created_at', 'is_active', 'thumbnail_preview')
    readonly_fields = ('created_at', 'thumbnail_preview', 'image_preview')

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html('<img src="{}" style="height: 50px;"/>', obj.thumbnail.url)
        return "-"
    thumbnail_preview.short_description = "Thumbnail"

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height: 150px;"/>', obj.image.url)
        return "-"
    image_preview.short_description = "Image"