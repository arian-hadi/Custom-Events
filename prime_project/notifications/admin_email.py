"""Operational administrator mail with a transactional outbox and explicit retries."""
import logging
from datetime import timedelta
from urllib.parse import urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from .email_design import email_html

from .models import ADMIN_ALERT_TYPES, AdminEmailDelivery, AdminEmailSettings, parse_admin_recipients

logger = logging.getLogger(__name__)
KINDS = dict(ADMIN_ALERT_TYPES)


def configuration():
    return AdminEmailSettings.objects.first() or AdminEmailSettings()


def recipients_for(config):
    explicit = config.recipients or getattr(settings, 'ADMIN_NOTIFICATION_RECIPIENTS', '')
    if explicit:
        return parse_admin_recipients(explicit)
    return parse_admin_recipients(list(get_user_model().objects.filter(
        is_active=True, is_superuser=True,
    ).exclude(email='').values_list('email', flat=True)))


def queue_admin_alert(kind, instance, *, defer=False):
    """Called only for ready submissions. Persist before commit; send after commit."""
    if kind not in KINDS or not instance.pk:
        return
    try:
        # A savepoint prevents a queue-table failure from breaking a caller's transaction.
        with transaction.atomic():
            config = configuration()
            if not config.enabled or not getattr(config, kind):
                return
            recipients = recipients_for(config)
            if not recipients:
                logger.warning('Admin alert %s has no configured recipients', kind)
            for recipient in recipients:
                delivery, created = AdminEmailDelivery.objects.get_or_create(
                    kind=kind, object_label=instance._meta.label_lower,
                    object_id=instance.pk, recipient=recipient,
                )
                if created and not defer and getattr(settings, 'ADMIN_EMAIL_SEND_IMMEDIATELY', True):
                    transaction.on_commit(lambda pk=delivery.pk: safely_deliver(pk), robust=True)
    except Exception:
        logger.exception('Could not queue admin alert %s for record %s', kind, instance.pk)


def base_url():
    value = getattr(settings, 'ADMIN_NOTIFICATION_BASE_URL', '') or getattr(settings, 'V2_FRONTEND_URL', '')
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}):
        raise ValueError('Set ADMIN_NOTIFICATION_BASE_URL to the public website origin.')
    return value.rstrip('/')


def actionable(kind, item):
    if kind == 'youtube_blog_video':
        return item.channel.notify_admins and not item.blog_post_id
    if kind == 'editor_application':
        return item.channel_verified and item.status == 'pending' and not item.removal_requested
    if kind == 'editor_removal':
        return item.removal_requested
    if kind == 'edit_submission':
        # The existing preview flow confirms a submitted edit by making it verified.
        return item.status == 'verified'
    if kind == 'edit_report':
        return item.is_active and not item.is_resolved
    if kind == 'event_application':
        return item.status == 'pending'
    return False


def message_content(delivery, item):
    if delivery.kind == 'youtube_blog_video':
        subject = f'[Admin] YouTube video ready to prepare: {item.title}'[:200]
        review_url = base_url() + reverse('admin:platform_api_youtubeblogvideo_change', args=[item.pk])
        body = (f'A video was discovered for your blog workspace.\n\n{item.title}\n{item.video_url}\n\n'
                f'Open the workspace to review captions or add your script, download the AI brief, '
                f'and import your finished Markdown as a draft.\n{review_url}\n\nNothing has been published.')
        html = format_html('<p>A video is ready in your editorial workspace.</p><h2>{}</h2>'
                           '<p>Add or fetch the script, download the AI brief, then import the resulting Markdown.</p>'
                           '<p>Nothing has been published.</p>', item.title)
        return subject, body, email_html(subject, html, action_url=review_url, action_label='Prepare blog article')
    user = getattr(item, 'user', None) or item.applicant
    titles = {
        'editor_application': 'New editor application',
        'editor_removal': 'Editor removal requested',
        'edit_submission': 'New edit submitted',
        'edit_report': 'Edit reported for moderation',
        'event_application': 'New event application',
    }
    subject = f'[Admin] {titles[delivery.kind]} #{item.pk}'
    lines = [titles[delivery.kind], '', f'Reference: {item._meta.verbose_name} #{item.pk}',
             f'Submitted by: {user.username}', f'Account email: {user.email}']
    if delivery.kind in {'editor_application', 'editor_removal'}:
        lines += [f'Channel: {item.channel_name}', f'Platform: {item.get_channel_type_display()}',
                  f'Channel link: {item.channel_link}', f'Editing area: {item.get_editing_area_display()}',
                  f'Editing tool: {item.editing_tool}']
        if item.editing_area_other:
            lines.append(f'Other editing area: {item.editing_area_other}')
        if item.channel_screenshot:
            lines.append(f'Channel screenshot: {base_url()}{item.channel_screenshot.url}')
    elif delivery.kind == 'edit_submission':
        lines += [f'Title: {item.title}', f'Video: {item.video_url}', f'Channel: {item.channel_link}',
                  f'Description: {item.description}']
    elif delivery.kind == 'edit_report':
        lines += [f'Reported edit: {item.edit_submission.title}',
                  f'Video: {item.edit_submission.video_url}', f'Reason: {item.get_reason_display()}',
                  f'Details: {item.description}']
    elif delivery.kind == 'event_application':
        lines += [f'Event: {item.event.title}', f'Cover letter: {item.cover_letter}']
        for response in item.field_responses.select_related('field').all():
            value = getattr(response, f'value_{response.field.field_type}', '')
            lines.append(f'{response.field.name}: {value}')
    review_url = base_url() + reverse(f'admin:{item._meta.app_label}_{item._meta.model_name}_change', args=[item.pk])
    body = '\n'.join(lines) + f'\n\nReview application or report:\n{review_url}\n\nSign in with an authorized administrator account to review. Opening this link does not approve or reject anything.'
    html = format_html('<div style="white-space:pre-wrap">{}</div><p><a href="{}">Review in administration</a></p>',
                       '\n'.join(lines), review_url)
    return subject, body, email_html(subject, html, action_url=review_url, action_label='Review in administration')


def safely_deliver(pk):
    try:
        return deliver(pk)
    except Exception:
        # Database failures after a submission commits must not turn it into a failed request.
        logger.exception('Admin email delivery %s could not be processed', pk)
        return False


def deliver(pk):
    """Claim atomically so concurrent commands cannot send the same queued row."""
    now = timezone.now()
    claimed = AdminEmailDelivery.objects.filter(
        pk=pk, status__in=['pending', 'failed'], next_attempt_at__lte=now,
    ).update(status='sending', attempts=F('attempts') + 1, updated_at=now)
    if not claimed:
        return False
    delivery = AdminEmailDelivery.objects.get(pk=pk)
    try:
        config = configuration()
        # Respect disabled categories and removed recipients even for queued mail.
        if not config.enabled or not getattr(config, delivery.kind) or delivery.recipient not in recipients_for(config):
            AdminEmailDelivery.objects.filter(pk=pk).update(status='cancelled', last_error='Disabled or recipient removed.', updated_at=timezone.now())
            return False
        item = apps.get_model(delivery.object_label).objects.filter(pk=delivery.object_id).first()
        if item is None or not actionable(delivery.kind, item):
            AdminEmailDelivery.objects.filter(pk=pk).update(status='cancelled', last_error='No longer awaiting attention.', updated_at=timezone.now())
            return False
        subject, body, html = message_content(delivery, item)
        AdminEmailDelivery.objects.filter(pk=pk).update(subject=subject, body=body)
        backend = settings.EMAIL_BACKEND
        local_capture = backend == 'django.core.mail.backends.filebased.EmailBackend' and getattr(settings, 'V2_LOCAL_PREVIEW', False)
        if backend in {'django.core.mail.backends.console.EmailBackend', 'django.core.mail.backends.dummy.EmailBackend'} or (
                backend == 'django.core.mail.backends.filebased.EmailBackend' and not local_capture):
            raise ValueError('Configure a delivering email backend or the explicit local preview.')
        message = EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, [delivery.recipient])
        message.attach_alternative(html, 'text/html')
        if message.send(fail_silently=False) != 1:
            raise RuntimeError('Email backend did not accept the message.')
        AdminEmailDelivery.objects.filter(pk=pk).update(
            status='captured' if local_capture else 'sent', sent_at=timezone.now(),
            last_error='', updated_at=timezone.now(),
        )
        return True
    except Exception as exc:
        # Avoid storing SMTP credentials, full provider errors, or applicant data in diagnostics.
        AdminEmailDelivery.objects.filter(pk=pk).update(
            status='failed', last_error=f'{type(exc).__name__}: delivery failed; check email configuration and server logs.',
            next_attempt_at=timezone.now() + timedelta(minutes=min(2 ** min(delivery.attempts, 10), 1440)),
            updated_at=timezone.now(),
        )
        logger.warning('Admin email delivery %s failed (%s)', pk, type(exc).__name__)
        return False
