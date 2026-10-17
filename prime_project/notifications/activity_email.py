"""Optional account activity emails; security mail and marketing are separate."""
import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.html import format_html

from .campaigns import MAX_ATTEMPTS, delivery_mode, email_fingerprint, public_origin
from .models import MemberActivityDelivery, NotificationPreference
from .email_design import email_html

logger = logging.getLogger(__name__)
TOKEN_SALT = 'notifications.member-activity-unsubscribe.v1'
TYPE_FIELDS = {
    'application_approved': 'email_application_updates',
    'application_disapproved': 'email_application_updates',
    'ranking_updated': 'email_ranking_updates',
    'edit_of_week_daily': 'email_edit_reports',
    'title_unlocked': 'email_achievements',
    'edit_verified': 'email_edit_reports',
    'edit_rejected': 'email_edit_reports',
    'league_result': 'email_edit_reports',
    'league_ranking': 'email_ranking_updates',
    'league_award': 'email_achievements',
}


def is_v2():
    return bool(getattr(settings, 'V2_TRUST_GATEWAY_ADDRESS', False) or getattr(settings, 'V2_LOCAL_PREVIEW', False))


def preference_enabled(preferences, notification_type):
    field = TYPE_FIELDS.get(notification_type)
    if is_v2() and notification_type in {'ranking_updated', 'edit_of_week_daily'}:
        return False  # These legacy sources use follower counts / legacy scores.
    return bool(field and preferences and preferences.email_enabled and getattr(preferences, field))


def target_path(notification):
    kind, pk = notification.related_object_type, notification.related_object_id
    if kind == 'Announcement' and pk:
        return f'/community-updates?announcement={pk}'
    if kind == 'EditorApplication' and pk:
        return f'/applications/editors/{pk}'
    if kind == 'EventApplication' and pk:
        return f'/applications/events/{pk}'
    if kind == 'EditSubmission' and pk:
        return f'/account/edits/{pk}'
    if notification.notification_type.startswith('league_'):
        return '/editing-hub#league-rounds'
    if notification.notification_type == 'title_unlocked':
        return '/account/profile'
    return '/notifications'


def queue_activity_email(notification, preferences):
    if not getattr(settings, 'MEMBER_ACTIVITY_EMAIL_ENABLED', False):
        return False
    user = notification.user
    if not user.is_active or not user.is_verified or not user.email or not preference_enabled(preferences, notification.notification_type):
        return False
    _, created = MemberActivityDelivery.objects.get_or_create(notification=notification, defaults={
        'user': user, 'recipient': user.email,
        'subject': notification.title.replace('\r', ' ').replace('\n', ' ')[:200],
        'body': notification.message, 'target_path': target_path(notification),
    })
    return created


def cancel_opted_out_activity(user_id):
    preferences = NotificationPreference.objects.filter(user_id=user_id).first()
    rows = MemberActivityDelivery.objects.filter(user_id=user_id, status__in=['pending', 'failed'])
    allowed = [kind for kind in TYPE_FIELDS if preference_enabled(preferences, kind)]
    rows.exclude(notification__notification_type__in=allowed).update(
        status='cancelled', last_error='Member unsubscribed.', updated_at=timezone.now(),
    )


def unsubscribe_token(user):
    return signing.dumps({'user': user.pk, 'email': email_fingerprint(user.email)}, salt=TOKEN_SALT, compress=True)


def token_user(token):
    from django.contrib.auth import get_user_model
    try:
        data = signing.loads(token, salt=TOKEN_SALT)
        if not isinstance(data, dict) or type(data.get('user')) is not int or not isinstance(data.get('email'), str):
            return None
        user = get_user_model().objects.filter(pk=data['user']).first()
        if user and constant_time_compare(email_fingerprint(user.email), data['email']):
            return user
    except (signing.BadSignature, ValueError, TypeError):
        pass
    return None


def unsubscribe(user):
    from django.db import transaction
    from .campaigns import cancel_opted_out_deliveries
    with transaction.atomic():
        preferences, _ = NotificationPreference.objects.get_or_create(user=user)
        NotificationPreference.objects.filter(pk=preferences.pk).update(email_enabled=False, updated_at=timezone.now())
        cancel_opted_out_activity(user.pk)
        cancel_opted_out_deliveries(user.pk)


def delivery_state():
    try:
        if not getattr(settings, 'MEMBER_ACTIVITY_EMAIL_ENABLED', False):
            raise ValueError('disabled')
        public_origin()
        mode = delivery_mode()
        return {'email_activity_delivery_active': mode == 'sent', 'email_activity_capture_mode': mode == 'captured'}
    except (ValueError, TypeError):
        return {'email_activity_delivery_active': False, 'email_activity_capture_mode': False}


def deliver_activity_email(delivery_id):
    if not getattr(settings, 'MEMBER_ACTIVITY_EMAIL_ENABLED', False):
        return False
    now = timezone.now()
    claimed = MemberActivityDelivery.objects.filter(
        pk=delivery_id, status__in=['pending', 'failed'], next_attempt_at__lte=now, attempts__lt=MAX_ATTEMPTS,
    ).update(status='sending', attempts=F('attempts') + 1, updated_at=now)
    if not claimed:
        return False
    row = MemberActivityDelivery.objects.select_related('user', 'notification').filter(pk=delivery_id).first()
    if not row:
        return False
    accepted = False
    try:
        user = row.user
        preferences = NotificationPreference.objects.filter(user_id=user.pk).first()
        if (not user.is_active or not user.is_verified or user.email != row.recipient
                or row.notification.user_id != user.pk or not preference_enabled(preferences, row.notification.notification_type)):
            MemberActivityDelivery.objects.filter(pk=row.pk).update(
                status='cancelled', last_error='Member opted out, account unavailable, or address changed.', updated_at=timezone.now(),
            )
            return False
        origin, mode = public_origin(), delivery_mode()
        token = unsubscribe_token(user)
        unsubscribe_url = origin + reverse('member_email:activity_unsubscribe', args=[token])
        one_click_url = origin + reverse('member_email:activity_one_click', args=[token])
        preferences_url = origin + '/account/preferences'
        # Only internal application paths are created by the queue.
        path = row.target_path if row.target_path.startswith('/') and not row.target_path.startswith('//') else '/notifications'
        details_url = origin + path
        body = (f'{row.body}\n\nView details: {details_url}\n\n'
                f'Manage email preferences: {preferences_url}\nStop optional member emails: {unsubscribe_url}\n'
                'Account security emails and order receipts are separate.')
        html = format_html(
            '<div style="white-space:pre-wrap">{}</div><p><a href="{}">View details</a></p>'
            '<p><a href="{}">Manage email preferences</a> · <a href="{}">Stop optional member emails</a></p>'
            '<p>Account security emails and order receipts are separate.</p>',
            row.body, details_url, preferences_url, unsubscribe_url,
        )
        headers = {'List-Unsubscribe': f'<{one_click_url}>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
        message = EmailMultiAlternatives(row.subject, body, settings.DEFAULT_FROM_EMAIL, [row.recipient], headers=headers)
        message.attach_alternative(email_html(row.subject, html, action_url=details_url), 'text/html')
        if message.send(fail_silently=False) != 1:
            raise RuntimeError('The email backend did not accept the message.')
        accepted = True
        MemberActivityDelivery.objects.filter(pk=row.pk).update(status=mode, sent_at=timezone.now(), last_error='', updated_at=timezone.now())
        return True
    except Exception as exc:
        if accepted:
            logger.warning('Activity email %s accepted; completion recording failed (%s).', row.pk, type(exc).__name__)
            return True  # Never automatically retry after confirmed SMTP acceptance.
        MemberActivityDelivery.objects.filter(pk=row.pk).update(
            status='failed', last_error=f'{type(exc).__name__}: activity email delivery failed; check configuration.',
            next_attempt_at=timezone.now() + timedelta(minutes=2 ** min(row.attempts, 10)), updated_at=timezone.now(),
        )
        logger.warning('Activity email %s failed (%s).', row.pk, type(exc).__name__)
        return False
