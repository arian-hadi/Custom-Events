from django.contrib import admin
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Notification, NotificationPreference, AdminEmailSettings, AdminEmailDelivery
from .models import MemberEmailSettings, MemberEmailCampaign, MemberEmailDelivery
from .models import MemberActivityDelivery, LeagueNotificationEvent


class SuperuserOnlyAdmin(admin.ModelAdmin):
    """Alert destinations and application contents are owner-level configuration."""
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdminEmailSettings)
class AdminEmailSettingsAdmin(SuperuserOnlyAdmin):
    fieldsets = (
        ('Delivery', {'fields': ('enabled', 'recipients')}),
        ('Notify administrators about', {'fields': (
            'editor_application', 'editor_removal', 'edit_submission', 'edit_report', 'event_application', 'youtube_blog_video',
        )}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not AdminEmailSettings.objects.exists()


@admin.register(AdminEmailDelivery)
class AdminEmailDeliveryAdmin(SuperuserOnlyAdmin):
    list_display = ('kind', 'object_id', 'recipient', 'status', 'attempts', 'created_at', 'sent_at')
    list_filter = ('status', 'kind')
    search_fields = ('recipient', 'subject')
    readonly_fields = tuple(field.name for field in AdminEmailDelivery._meta.fields)
    actions = ['retry_failed', 'retry_interrupted']

    def has_add_permission(self, request):
        return False

    @admin.action(description='Retry selected failed emails now')
    def retry_failed(self, request, queryset):
        from .admin_email import safely_deliver
        if not self.has_change_permission(request):
            return
        ids = list(queryset.filter(status='failed').values_list('pk', flat=True))
        with transaction.atomic():
            AdminEmailDelivery.objects.filter(pk__in=ids, status='failed').update(next_attempt_at=timezone.now())
            for pk in ids:
                transaction.on_commit(lambda pk=pk: safely_deliver(pk), robust=True)
        self.message_user(request, f'{len(ids)} failed delivery attempt(s) requested. Refresh to see the results.')

    @admin.action(description='Retry interrupted sends older than 15 minutes (may send duplicates)')
    def retry_interrupted(self, request, queryset):
        from .admin_email import safely_deliver
        if not self.has_change_permission(request):
            return
        cutoff = timezone.now() - timedelta(minutes=15)
        count = 0
        with transaction.atomic():
            for pk in queryset.filter(status='sending', updated_at__lt=cutoff).values_list('pk', flat=True):
                changed = AdminEmailDelivery.objects.filter(pk=pk, status='sending', updated_at__lt=cutoff).update(
                    status='failed', next_attempt_at=timezone.now(), updated_at=timezone.now(),
                    last_error='Interrupted delivery manually requeued by an administrator.',
                )
                if changed:
                    count += 1
                    transaction.on_commit(lambda pk=pk: safely_deliver(pk), robust=True)
        self.message_user(request, f'{count} interrupted delivery attempt(s) requested. Provider acceptance before interruption may cause a duplicate email.')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'user__email', 'title', 'message')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('user', 'title', 'message', 'notification_type')
        }),
        ('Status', {
            'fields': ('is_read', 'created_at')
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id'),
            'classes': ('collapse',)
        }),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_enabled', 'in_app_enabled', 'updated_at')
    list_filter = ('email_enabled', 'in_app_enabled', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Channel Preferences', {
            'fields': ('email_enabled', 'in_app_enabled')
        }),
        ('Email Type Preferences', {
            'fields': (
                'email_application_updates',
                'email_ranking_updates',
                'email_edit_reports',
                'email_achievements',
                'email_newsletter',
                'email_blog_updates',
                'email_shop_updates',
            ),
            'classes': ('collapse',)
        }),
        ('In-App Type Preferences', {
            'fields': (
                'in_app_application_updates',
                'in_app_ranking_updates',
                'in_app_edit_reports',
                'in_app_achievements'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(MemberEmailSettings)
class MemberEmailSettingsAdmin(SuperuserOnlyAdmin):
    fields = ('automatic_blog', 'blog_enabled_since', 'automatic_shop', 'shop_enabled_since')
    readonly_fields = ('blog_enabled_since', 'shop_enabled_since')

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not MemberEmailSettings.objects.exists()


@admin.register(MemberEmailCampaign)
class MemberEmailCampaignAdmin(SuperuserOnlyAdmin):
    list_display = ('subject', 'topic', 'status', 'scheduled_at', 'queued_at')
    list_filter = ('topic', 'status')
    search_fields = ('subject',)
    fields = ('subject', 'topic', 'body', 'status', 'scheduled_at', 'source_key', 'created_by', 'queued_at', 'created_at', 'updated_at')
    readonly_fields = ('source_key', 'created_by', 'queued_at', 'created_at', 'updated_at')
    actions = ('schedule_now', 'cancel_selected')

    def get_readonly_fields(self, request, obj=None):
        if obj and (obj.queued_at or obj.status == 'cancelled'):
            return self.fields
        return self.readonly_fields

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'status':
            kwargs['choices'] = [('draft', 'Draft'), ('scheduled', 'Scheduled')]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        return super().save_model(request, obj, form, change)

    @admin.action(description='Schedule selected drafts for the next email worker run')
    def schedule_now(self, request, queryset):
        if not self.has_change_permission(request):
            return
        count = queryset.filter(status='draft', queued_at=None).update(status='scheduled', scheduled_at=timezone.now(), updated_at=timezone.now())
        self.message_user(request, f'{count} draft(s) scheduled. The member_email_tick worker must run to deliver them.')

    @admin.action(description='Cancel selected campaigns and unsent deliveries')
    def cancel_selected(self, request, queryset):
        from .campaigns import cancel_campaign
        if not self.has_change_permission(request):
            return
        count = 0
        for pk in queryset.exclude(status__in=['cancelled', 'completed']).values_list('pk', flat=True):
            cancel_campaign(pk)
            count += 1
        self.message_user(request, f'{count} campaign(s) cancelled. Email already accepted by a provider cannot be recalled.')


@admin.register(MemberEmailDelivery)
class MemberEmailDeliveryAdmin(SuperuserOnlyAdmin):
    list_display = ('campaign', 'recipient', 'status', 'attempts', 'next_attempt_at', 'sent_at')
    list_filter = ('status', 'campaign__topic')
    search_fields = ('recipient', 'campaign__subject')
    readonly_fields = tuple(field.name for field in MemberEmailDelivery._meta.fields)
    actions = ('retry_failed', 'retry_interrupted')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Requeue selected failed emails (preferences are checked again)')
    def retry_failed(self, request, queryset):
        if not self.has_change_permission(request):
            return
        count = queryset.filter(status='failed', campaign__status='queued').update(
            attempts=0, next_attempt_at=timezone.now(), updated_at=timezone.now(),
        )
        self.message_user(request, f'{count} failed email(s) will be retried on the next worker run.')

    @admin.action(description='Requeue interrupted sends older than 15 minutes (may duplicate email)')
    def retry_interrupted(self, request, queryset):
        if not self.has_change_permission(request):
            return
        count = queryset.filter(status='sending', campaign__status='queued', updated_at__lt=timezone.now()-timedelta(minutes=15)).update(
            status='failed', attempts=0, next_attempt_at=timezone.now(), updated_at=timezone.now(),
            last_error='Interrupted send manually requeued; earlier provider acceptance may cause a duplicate.',
        )
        self.message_user(request, f'{count} interrupted email(s) requeued. SMTP acceptance before interruption may cause duplicates.')


@admin.register(MemberActivityDelivery)
class MemberActivityDeliveryAdmin(SuperuserOnlyAdmin):
    list_display = ('notification', 'recipient', 'status', 'attempts', 'next_attempt_at', 'sent_at')
    list_filter = ('status', 'notification__notification_type')
    search_fields = ('recipient', 'subject')
    readonly_fields = tuple(field.name for field in MemberActivityDelivery._meta.fields)
    actions = ('retry_failed', 'retry_interrupted')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Requeue failed activity emails (preferences checked again)')
    def retry_failed(self, request, queryset):
        if not self.has_change_permission(request):
            return
        count = queryset.filter(status='failed').update(attempts=0, next_attempt_at=timezone.now(), updated_at=timezone.now())
        self.message_user(request, f'{count} failed email(s) requeued for the worker.')

    @admin.action(description='Requeue interrupted sends older than 15 minutes (may duplicate email)')
    def retry_interrupted(self, request, queryset):
        if not self.has_change_permission(request):
            return
        count = queryset.filter(status='sending', updated_at__lt=timezone.now()-timedelta(minutes=15)).update(
            status='failed', attempts=0, next_attempt_at=timezone.now(), updated_at=timezone.now(),
            last_error='Interrupted send manually requeued; earlier provider acceptance may cause a duplicate.')
        self.message_user(request, f'{count} interrupted send(s) requeued. Provider acceptance before interruption may cause duplicates.')


@admin.register(LeagueNotificationEvent)
class LeagueNotificationEventAdmin(SuperuserOnlyAdmin):
    list_display = ('event_key', 'kind', 'email_eligible', 'processed_at', 'created_at')
    readonly_fields = tuple(field.name for field in LeagueNotificationEvent._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False
