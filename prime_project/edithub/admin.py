from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.html import mark_safe
from .application_policy import active_application, activates_application, SINGLE_CHANNEL_MESSAGE
from .forms import EditorApplicationAdminForm

from .models import EditorApplication, EditSubmission, EditUpvote, EditReport, Tournament, TournamentMatchVote, WeekWinner, EditorTitle, UserTitleUnlock


@admin.register(EditorApplication)
class EditorApplicationAdmin(admin.ModelAdmin):
    form = EditorApplicationAdminForm

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Match the API's member lock so an admin add and a member application
        # cannot both pass their eligibility checks at the same time.
        with transaction.atomic():
            user_id = request.POST.get('user', '') if request.method == 'POST' else ''
            if user_id.isdecimal():
                get_user_model().objects.select_for_update().filter(pk=user_id).first()
            return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = [
        'user', 'channel_name', 'channel_type', 'editing_tool', 'editing_area',
        'follower_count', 'status', 'channel_verified', 'league_eligible', 'rank_position', 'applied_date'
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
            'fields': ('editing_area', 'editing_area_other', 'editing_tool', 'selected_title')
        }),
        ('Verification & Consent', {
            'fields': ('channel_verified', 'data_consent'),
            'description': 'Channel verified records the member’s ownership confirmation. Approval alone does not record that declaration. An approved member can finish confirmation on their existing V2 application page; they do not need to apply again.'
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

    @admin.display(boolean=True, description='Channel ready for league')
    def league_eligible(self, obj):
        return obj.status == 'accepted' and obj.channel_verified and not obj.removal_requested

    def channel_screenshot_preview(self, obj):
        if obj and obj.channel_screenshot:
            return mark_safe(f'<img src="{obj.channel_screenshot.url}" style="max-width: 400px; height: auto;" />')
        return "No screenshot uploaded"

    channel_screenshot_preview.short_description = "Channel Screenshot"
    
    def accept_applications(self, request, queryset):
        """
        Bulk accept applications.

        Important: we must call save() after changing status on each instance
        so that EditorApplication.save() can run its logic to:
        - Recalculate rankings
        - Download and set the user's profile_picture from channel_thumbnail
        """
        from django.utils import timezone
        updated = 0

        skipped = 0
        for selected in queryset:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=selected.user_id)
                app = EditorApplication.objects.get(pk=selected.pk)
                if (activates_application(app, app.user, 'accepted', app.removal_requested)
                        and active_application(app.user, exclude_id=app.pk)):
                    skipped += 1
                    continue
                if app.status != 'accepted':
                    app.status = 'accepted'
                    updated += 1
                app.reviewed_date = timezone.now()
                app.reviewed_by = request.user
                app.save()

        if updated:
            self.message_user(request, f'{updated} application(s) accepted.')
        else:
            self.message_user(request, 'No applications were changed to accepted.')
        if skipped:
            self.message_user(request, f'{skipped} application(s) were not reactivated because the member already has an active channel. {SINGLE_CHANNEL_MESSAGE}', level='warning')
        unconfirmed = queryset.filter(status='accepted', channel_verified=False, removal_requested=False).count()
        if unconfirmed:
            self.message_user(request, f'{unconfirmed} approved application(s) still need the member to confirm channel ownership on their existing application page.', level='warning')
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


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'semi_finals_active', 'finals_active', 'participant_1', 'participant_2', 'participant_3', 'participant_4', 'created_date')
    list_filter = ('is_active', 'semi_finals_active', 'finals_active', 'created_date')
    readonly_fields = ('created_date', 'updated_date')
    fieldsets = (
        ('Tournament Information', {
            'fields': ('name', 'is_active')
        }),
        ('Phase Status', {
            'fields': ('semi_finals_active', 'finals_active'),
            'description': 'Control which phases are currently active. Semi-finals should be active first, then activate finals when ready.'
        }),
        ('Semi-Final 1', {
            'fields': ('participant_1', 'participant_1_edit_link', 'participant_2', 'participant_2_edit_link'),
            'description': 'Select the two participants for Semi-Final 1 (left side of bracket) and add their edit links (YouTube or TikTok URLs)'
        }),
        ('Semi-Final 2', {
            'fields': ('participant_3', 'participant_3_edit_link', 'participant_4', 'participant_4_edit_link'),
            'description': 'Select the two participants for Semi-Final 2 (right side of bracket) and add their edit links (YouTube or TikTok URLs)'
        }),
        ('Finals', {
            'fields': ('finalist_1', 'finalist_1_edit_link', 'finalist_2', 'finalist_2_edit_link'),
            'description': 'Select the winners from semi-finals and add their edit links. Finalist 1 should be the winner from Semi-Final 1 (left side), Finalist 2 should be the winner from Semi-Final 2 (right side). Only fill these when finals phase is active.'
        }),
        ('Timestamps', {
            'fields': ('created_date', 'updated_date'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('participant_1', 'participant_2', 'participant_3', 'participant_4',
                                 'finalist_1', 'finalist_2',
                                 'participant_1__user', 'participant_2__user', 'participant_3__user', 'participant_4__user',
                                 'finalist_1__user', 'finalist_2__user')


@admin.register(TournamentMatchVote)
class TournamentMatchVoteAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'match_type', 'voter', 'voted_for', 'created_date')
    list_filter = ('tournament', 'match_type', 'created_date')
    readonly_fields = ('created_date',)
    search_fields = ('voter__username', 'voted_for__channel_name', 'tournament__name')
    raw_id_fields = ('tournament', 'voter', 'voted_for')


@admin.register(WeekWinner)
class WeekWinnerAdmin(admin.ModelAdmin):
    list_display = ('week_start', 'week_rank', 'channel_name', 'user', 'channel_type', 'calculated_points', 'created_date')
    list_filter = ('week_rank', 'channel_type', 'week_start', 'created_date')
    search_fields = ('user__username', 'channel_name', 'video_url', 'title')
    readonly_fields = ('created_date',)  # Only created_date is readonly
    date_hierarchy = 'week_start'
    ordering = ('-week_start', 'week_rank')
    
    fieldsets = (
        ('Winner Information', {
            'fields': ('week_start', 'week_rank', 'calculated_points')
        }),
        ('User & Channel', {
            'fields': ('user', 'channel_name', 'channel_type')
        }),
        ('Edit Details', {
            'fields': ('edit_submission', 'video_url', 'title')
        }),
        ('Timestamps', {
            'fields': ('created_date',),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        # When editing existing records, make most fields readonly
        # When adding new records (obj is None), allow all fields to be editable
        if obj:  # Editing existing record
            return ('edit_submission', 'user', 'video_url', 'week_start', 'week_rank', 'channel_type', 
                   'channel_name', 'title', 'calculated_points', 'created_date')
        else:  # Adding new record
            return ('created_date',)
    
    def has_add_permission(self, request):
        # Temporarily allow manual creation for testing purposes
        return True
    
    def has_delete_permission(self, request, obj=None):
        # Allow deletion for admin purposes (e.g., correcting mistakes)
        return request.user.is_superuser
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'edit_submission')


@admin.register(EditorTitle)
class EditorTitleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rarity', 'unlock_method', 'cost_coins', 'achievement_type', 'achievement_threshold', 'is_default', 'is_active', 'created_at')
    list_filter = ('rarity', 'unlock_method', 'achievement_type', 'is_default', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'unlock_requirement', 'achievement_group')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Title Information', {
            'fields': ('name', 'description', 'rarity', 'category')
        }),
        ('Unlock Method', {
            'fields': ('unlock_method', 'cost_coins', 'unlock_requirement'),
            'description': 'Choose how users can unlock this title: Coins, Achievement, Both, or Manual (Admin Only). For Manual titles, set unlock_requirement to explain how it can be received (e.g., "Won a one-time competition").'
        }),
        ('Achievement Settings', {
            'fields': ('achievement_type', 'achievement_threshold', 'tier_level', 'achievement_group'),
            'description': 'Configure achievement-based unlocking. Only used if unlock_method is "Achievement Only" or "Coins or Achievement"',
            'classes': ('collapse',)
        }),
        ('Availability', {
            'fields': ('is_default', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserTitleUnlock)
class UserTitleUnlockAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'unlock_method', 'unlocked_at')
    list_filter = ('unlock_method', 'unlocked_at')
    search_fields = ('user__username', 'title__name')
    readonly_fields = ('unlocked_at',)
    date_hierarchy = 'unlocked_at'
    raw_id_fields = ('user', 'title')
    fieldsets = (
        ('Unlock Information', {
            'fields': ('user', 'title', 'unlock_method'),
            'description': 'To manually unlock a title for a user, select the user and title, then set unlock_method to "Manual (Admin)".'
        }),
        ('Timestamps', {
            'fields': ('unlocked_at',),
            'classes': ('collapse',)
        }),
    )


# Register the additive V2 league operations and immutable audit pages.
from . import league_admin  # noqa: E402,F401
