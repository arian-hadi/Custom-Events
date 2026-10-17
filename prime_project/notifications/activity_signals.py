"""Lifecycle notifications cover Django admin and every member/API entry point."""
from uuid import uuid4
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from edithub.models import EditorApplication, EditSubmission, UserTitleUnlock
from edithub.league_models import WeeklyRevision, MonthlyAward
from events.models import EventApplication
from .activity_email import cancel_opted_out_activity, is_v2
from .manager import notification_manager
from .models import LeagueNotificationEvent, NotificationPreference


@receiver(pre_save, sender=EditorApplication, dispatch_uid='activity_editor_previous')
@receiver(pre_save, sender=EventApplication, dispatch_uid='activity_event_previous')
@receiver(pre_save, sender=EditSubmission, dispatch_uid='activity_edit_previous')
def previous_status(sender, instance, raw=False, update_fields=None, using='default', **kwargs):
    instance._activity_previous = None
    instance._activity_key = uuid4().hex
    if not raw and instance.pk and (update_fields is None or 'status' in update_fields):
        instance._activity_previous = sender.objects.using(using).filter(pk=instance.pk).values_list('status', flat=True).first()


@receiver(post_save, sender=EditorApplication, dispatch_uid='activity_editor_decision')
@receiver(post_save, sender=EventApplication, dispatch_uid='activity_event_decision')
@receiver(post_save, sender=EditSubmission, dispatch_uid='activity_edit_decision')
def status_changed(sender, instance, created, raw=False, using='default', **kwargs):
    old = getattr(instance, '_activity_previous', None)
    if raw or created or old is None:
        return
    status = sender.objects.using(using).filter(pk=instance.pk).values_list('status', flat=True).first()
    if old == status:
        return
    if sender is EditSubmission:
        if status not in {'verified', 'rejected'}:
            return
        user = instance.user
        title = 'Edit verified' if status == 'verified' else 'Edit review update'
        message = f'Your edit "{instance.title or "Untitled edit"}" is {status}. Open your edits to review its status.'
        kind = 'edit_verified' if status == 'verified' else 'edit_rejected'
    else:
        if status not in {'accepted', 'rejected'}:
            return
        user = instance.applicant if sender is EventApplication else instance.user
        label = f'event "{instance.event.title}"' if sender is EventApplication else f'{instance.get_channel_type_display()} editor'
        title = 'Application approved' if status == 'accepted' else 'Application review update'
        message = f'Your {label} application has been {"approved" if status == "accepted" else "rejected"}. Open your applications for details.'
        kind = 'application_approved' if status == 'accepted' else 'application_disapproved'
    notification_manager.create_notification(user, title, message, kind, related_object=instance,
        event_key=f'{sender._meta.label_lower}:{instance.pk}:{instance._activity_key}')


@receiver(post_save, sender=UserTitleUnlock, dispatch_uid='activity_title_unlock')
def title_unlocked(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    # Old automatic point/placement achievements are not V2 league achievements.
    if is_v2() and instance.unlock_method == 'achievement':
        return
    notification_manager.create_notification(instance.user, 'New editor title',
        f'You have unlocked "{instance.title.name}". Choose it in your profile.', 'title_unlocked',
        related_object=instance.title, event_key=f'title-unlock:{instance.pk}')


@receiver(post_save, sender=NotificationPreference, dispatch_uid='activity_preferences_changed')
def preferences_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        cancel_opted_out_activity(instance.user_id)


@receiver(post_save, sender=WeeklyRevision, dispatch_uid='activity_weekly_revision')
@receiver(post_save, sender=MonthlyAward, dispatch_uid='activity_monthly_award')
def league_event(sender, instance, created, raw=False, using='default', **kwargs):
    if raw or not created:
        return
    kind = {WeeklyRevision: 'weekly', MonthlyAward: 'monthly'}[sender]
    event, _ = LeagueNotificationEvent.objects.using(using).get_or_create(
        event_key=f'{kind}:{instance.pk}', defaults={'kind': kind, 'object_id': instance.pk,
        'email_eligible': bool(getattr(settings, 'MEMBER_ACTIVITY_EMAIL_ENABLED', False))})
    from .league_activity import process_league_event
    transaction.on_commit(lambda: process_league_event(event.pk), using=using, robust=True)
