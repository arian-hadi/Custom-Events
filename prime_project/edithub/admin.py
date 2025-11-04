from django.contrib import admin
from .models import EditorApplication


@admin.register(EditorApplication)
class EditorApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'channel_name', 'channel_type', 'editing_area', 
        'follower_count', 'status', 'rank_position', 'applied_date'
    ]
    list_filter = ['status', 'channel_type', 'editing_area', 'applied_date', 'removal_requested']
    search_fields = ['user__username', 'user__email', 'channel_name', 'channel_link']
    readonly_fields = ['applied_date', 'updated_date', 'reviewed_date', 'rank_position']
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Channel Information', {
            'fields': ('channel_link', 'channel_type', 'channel_name', 'channel_thumbnail', 'follower_count')
        }),
        ('Application Details', {
            'fields': ('editing_area', 'editing_area_other')
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
