from django.contrib import admin
from django.utils.html import mark_safe

from .models import EditorApplication, EditSubmission, EditUpvote, EditReport


@admin.register(EditorApplication)
class EditorApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'channel_name', 'channel_type', 'editing_tool', 'editing_area',
        'follower_count', 'status', 'rank_position', 'applied_date'
    ]
    list_filter = ['status', 'channel_type', 'editing_area', 'editing_tool', 'applied_date', 'removal_requested']
    search_fields = ['user__username', 'user__email', 'channel_name', 'channel_link', 'editing_tool']
    readonly_fields = ['applied_date', 'updated_date', 'reviewed_date', 'rank_position', 'channel_screenshot_preview']
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Channel Information', {
            'fields': (
                'channel_link', 'channel_type', 'channel_name', 'channel_thumbnail',
                'channel_screenshot', 'channel_screenshot_preview', 'follower_count'
            )
        }),
        ('Application Details', {
            'fields': ('editing_area', 'editing_area_other', 'editing_tool')
        }),
        ('Verification & Consent', {
            'fields': ('channel_verified', 'data_consent')
        }),
        ('Status & Review', {
            'fields': ('status', 'reviewed_by', 'reviewed_date', 'rank_position')
        }),
        ('Removal Request', {
            'fields': ('removal_requested', 'removal_requested_date')
        }),
        ('Timestamps', {
            'fields': ('applied_date', 'updated_date'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['accept_applications', 'reject_applications']

    def channel_screenshot_preview(self, obj):
        if obj and obj.channel_screenshot:
            return mark_safe(f'<img src="{obj.channel_screenshot.url}" style="max-width: 400px; height: auto;" />')
        return "No screenshot uploaded"

    channel_screenshot_preview.short_description = "Channel Screenshot"
    
    def accept_applications(self, request, queryset):
        """Bulk accept applications"""
        updated = queryset.update(status='accepted')
        from django.utils import timezone
        from .models import EditorApplication
        for app in queryset.filter(status='accepted'):
            app.reviewed_date = timezone.now()
            app.reviewed_by = request.user
            app.save()
        EditorApplication.update_rank_positions()
        self.message_user(request, f'{updated} applications accepted.')
    accept_applications.short_description = "Accept selected applications"
    
    def reject_applications(self, request, queryset):
        """Bulk reject applications"""
        updated = queryset.update(status='rejected')
        from django.utils import timezone
        for app in queryset.filter(status='rejected'):
            app.reviewed_date = timezone.now()
            app.reviewed_by = request.user
            app.save()
        self.message_user(request, f'{updated} applications rejected.')
    reject_applications.short_description = "Reject selected applications"


@admin.register(EditSubmission)
class EditSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'channel_name', 'channel_type', 'scheduled_week',
        'status', 'submitted_date', 'upvote_count', 'report_count', 'is_featured'
    )
    list_filter = (
        'channel_type', 'status', 'scheduled_week', 'is_featured', 'week_rank'
    )
    search_fields = ('user__username', 'channel_name', 'video_url')
    readonly_fields = ('submitted_date', 'updated_date', 'verified_date', 'upvote_count', 'report_count')
    date_hierarchy = 'submitted_date'


@admin.register(EditUpvote)
class EditUpvoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'edit_submission', 'is_active', 'created_date')
    list_filter = ('is_active', 'created_date')
    search_fields = ('user__username', 'edit_submission__channel_name')
    readonly_fields = ('created_date',)


@admin.register(EditReport)
class EditReportAdmin(admin.ModelAdmin):
    list_display = ('edit_submission', 'user', 'reason', 'is_active', 'is_resolved', 'created_date')
    list_filter = ('reason', 'is_active', 'is_resolved')
    search_fields = ('edit_submission__channel_name', 'user__username', 'description')
    readonly_fields = ('created_date', 'resolved_date')
