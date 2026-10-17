"""Opt-in member campaigns, a durable outbox, and polling-based publication discovery."""
import hashlib
import logging
from datetime import timedelta
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.html import format_html, strip_tags
from .email_design import email_html

from .models import MemberEmailCampaign, MemberEmailDelivery, MemberEmailSettings, NotificationPreference

logger = logging.getLogger(__name__)
TOPIC_FIELDS = {'newsletter': 'email_newsletter', 'blog_updates': 'email_blog_updates', 'shop_updates': 'email_shop_updates'}
TOKEN_SALT = 'notifications.member-campaign-unsubscribe.v1'
MAX_ATTEMPTS = 5


def public_origin():
    value = getattr(settings, 'MEMBER_EMAIL_BASE_URL', '').strip().rstrip('/')
    parsed = urlsplit(value)
    local_gateway = (getattr(settings, 'DEBUG', False) and getattr(settings, 'V2_TRUST_GATEWAY_ADDRESS', False)
                     and parsed.hostname in {'localhost', '127.0.0.1', '::1'})
    allowed_schemes = {'https', 'http'} if getattr(settings, 'V2_LOCAL_PREVIEW', False) or local_gateway else {'https'}
    if (parsed.scheme not in allowed_schemes or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('Set MEMBER_EMAIL_BASE_URL to the public HTTPS website origin.')
    return value


def delivery_mode():
    backend = settings.EMAIL_BACKEND
    if (backend == 'django.core.mail.backends.smtp.EmailBackend' and getattr(settings, 'EMAIL_HOST', '') == 'mailpit'
            and getattr(settings, 'DEBUG', False)
            and (getattr(settings, 'V2_LOCAL_PREVIEW', False) or getattr(settings, 'V2_TRUST_GATEWAY_ADDRESS', False))):
        return 'captured'
    if backend == 'django.core.mail.backends.filebased.EmailBackend' and getattr(settings, 'V2_LOCAL_PREVIEW', False):
        return 'captured'
    if backend in {'django.core.mail.backends.console.EmailBackend', 'django.core.mail.backends.dummy.EmailBackend',
                   'django.core.mail.backends.filebased.EmailBackend'}:
        raise ValueError('Configure a delivering email backend or the explicit local preview.')
    return 'sent'


def delivery_state():
    if not getattr(settings, 'MEMBER_EMAIL_ENABLED', False):
        return {'email_campaign_delivery_active': False, 'email_campaign_capture_mode': False}
    try:
        public_origin()
        if not getattr(settings, 'MEMBER_EMAIL_POSTAL_ADDRESS', '').strip():
            raise ValueError('Configure the sender postal address.')
        mode = delivery_mode()
    except (TypeError, ValueError):
        return {'email_campaign_delivery_active': False, 'email_campaign_capture_mode': False}
    return {'email_campaign_delivery_active': mode == 'sent', 'email_campaign_capture_mode': mode == 'captured'}


def email_fingerprint(email):
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def unsubscribe_token(user):
    # No short expiry: old campaign mail must retain a usable opt-out link.
    # Tying the capability to the email invalidates it after an address change.
    return signing.dumps({'user': user.pk, 'email': email_fingerprint(user.email)}, salt=TOKEN_SALT, compress=True)


def token_user(token):
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
    with transaction.atomic():
        preferences, _ = NotificationPreference.objects.get_or_create(user=user)
        NotificationPreference.objects.filter(pk=preferences.pk).update(
            **{field: False for field in TOPIC_FIELDS.values()}, updated_at=timezone.now(),
        )
        cancel_opted_out_deliveries(user.pk)


def cancel_opted_out_deliveries(user_id):
    """Opting out cancels the old audience snapshot even if the user opts in again."""
    preferences = NotificationPreference.objects.filter(user_id=user_id).first()
    rows = MemberEmailDelivery.objects.filter(user_id=user_id, status__in=['pending', 'failed'])
    if preferences and preferences.email_enabled:
        topics = [topic for topic, field in TOPIC_FIELDS.items() if not getattr(preferences, field)]
        rows = rows.filter(campaign__topic__in=topics)
    campaign_ids = list(rows.values_list('campaign_id', flat=True).distinct())
    rows.update(status='cancelled', last_error='Member unsubscribed.', updated_at=timezone.now())
    for campaign_id in campaign_ids:
        finish_campaign(campaign_id)


def eligible_users(topic):
    return get_user_model().objects.filter(
        is_active=True, is_verified=True, notification_preferences__email_enabled=True,
        **{f'notification_preferences__{TOPIC_FIELDS[topic]}': True},
    ).exclude(email='')


def queue_campaign(campaign_id, now=None):
    """Freeze content and audience in one transaction; retries cannot append new users."""
    if not getattr(settings, 'MEMBER_EMAIL_ENABLED', False):
        return 0
    now = now or timezone.now()
    with transaction.atomic():
        campaign = MemberEmailCampaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status != 'scheduled' or campaign.scheduled_at > now or campaign.queued_at:
            return 0
        campaign.full_clean()
        changed = MemberEmailCampaign.objects.filter(pk=campaign.pk, status='scheduled', queued_at=None).update(
            status='queued', queued_at=now, updated_at=now,
        )
        if not changed:
            return 0
        rows = [MemberEmailDelivery(campaign=campaign, user=user, recipient=user.email)
                for user in eligible_users(campaign.topic).iterator()]
        MemberEmailDelivery.objects.bulk_create(rows, batch_size=500)
        if not rows:
            MemberEmailCampaign.objects.filter(pk=campaign.pk).update(status='completed', updated_at=now)
        return len(rows)


def cancel_campaign(campaign_id):
    with transaction.atomic():
        campaign = MemberEmailCampaign.objects.select_for_update().filter(pk=campaign_id).first()
        if not campaign or campaign.status in {'completed', 'cancelled'}:
            return 0
        MemberEmailCampaign.objects.filter(pk=campaign_id).update(status='cancelled', updated_at=timezone.now())
        return MemberEmailDelivery.objects.filter(campaign_id=campaign_id, status__in=['pending', 'failed']).update(
            status='cancelled', last_error='Campaign cancelled.', updated_at=timezone.now(),
        )


def finish_campaign(campaign_id):
    if not MemberEmailDelivery.objects.filter(campaign_id=campaign_id, status__in=['pending', 'failed', 'sending']).exists():
        MemberEmailCampaign.objects.filter(pk=campaign_id, status='queued').update(status='completed', updated_at=timezone.now())


def reconcile_completed_campaigns(limit=100):
    """Repair completion bookkeeping after a crash or account deletion, without sending."""
    unfinished = MemberEmailDelivery.objects.filter(campaign_id=OuterRef('pk'), status__in=['pending', 'failed', 'sending'])
    ids = list(MemberEmailCampaign.objects.filter(status='queued').annotate(has_unfinished=Exists(unfinished)).filter(
        has_unfinished=False,
    ).values_list('pk', flat=True)[:limit])
    return MemberEmailCampaign.objects.filter(pk__in=ids, status='queued').update(status='completed', updated_at=timezone.now())


def automatic_source_active(campaign):
    if not campaign.source_key:
        return True
    config = MemberEmailSettings.objects.filter(pk=1).first()
    kind, _, object_id = campaign.source_key.partition(':')
    if kind == 'blog':
        from platform_api.models import BlogPost
        return bool(config and config.automatic_blog and BlogPost.objects.filter(
            pk=object_id, status='published', published_at__gte=config.blog_enabled_since, published_at__lte=timezone.now(),
        ).exists())
    if kind == 'shop':
        from shop.models import Product
        return bool(config and config.automatic_shop and Product.objects.filter(
            pk=object_id, is_active=True, created_at__gte=config.shop_enabled_since,
        ).exclude(ecommerce_platform='amazon').exists())
    return False


def deliver_member_email(delivery_id):
    """Atomic claim followed by a fresh opt-out check. SMTP acceptance is not inbox delivery."""
    if not getattr(settings, 'MEMBER_EMAIL_ENABLED', False):
        return False
    now = timezone.now()
    claimed = MemberEmailDelivery.objects.filter(
        pk=delivery_id, status__in=['pending', 'failed'], next_attempt_at__lte=now, attempts__lt=MAX_ATTEMPTS,
    ).update(status='sending', attempts=F('attempts') + 1, updated_at=now)
    if not claimed:
        return False
    delivery = MemberEmailDelivery.objects.select_related('campaign', 'user').filter(pk=delivery_id).first()
    if not delivery:  # The member may have deleted their account after the claim.
        return False
    accepted = False
    try:
        campaign = delivery.campaign
        user = delivery.user
        if (campaign.status != 'queued' or user.email != delivery.recipient
                or not eligible_users(campaign.topic).filter(pk=user.pk).exists() or not automatic_source_active(campaign)):
            MemberEmailDelivery.objects.filter(pk=delivery.pk).update(
                status='cancelled', last_error='Member opted out, address changed, or campaign no longer active.', updated_at=timezone.now(),
            )
            finish_campaign(campaign.pk)
            return False
        origin = public_origin()
        postal_address = getattr(settings, 'MEMBER_EMAIL_POSTAL_ADDRESS', '').strip()
        if not postal_address:
            raise ValueError('Configure MEMBER_EMAIL_POSTAL_ADDRESS.')
        mode = delivery_mode()
        token = unsubscribe_token(user)
        unsubscribe_url = origin + reverse('member_email:unsubscribe', args=[token])
        one_click_url = origin + reverse('member_email:one_click', args=[token])
        preferences_url = origin + '/account/preferences'
        body = f'{campaign.body}\n\n{postal_address}\n\nYou opted in to {campaign.get_topic_display().lower()}.\nManage email preferences: {preferences_url}\nStop all member email campaigns: {unsubscribe_url}'
        html = format_html(
            '<div style="white-space:pre-wrap">{}</div><p style="white-space:pre-wrap">{}</p><p>You opted in to {}.</p>'
            '<p><a href="{}">Manage email preferences</a> · <a href="{}">Unsubscribe from all member email campaigns</a></p>',
            campaign.body, postal_address, campaign.get_topic_display().lower(), preferences_url, unsubscribe_url,
        )
        headers = {'List-Unsubscribe': f'<{one_click_url}>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
        message = EmailMultiAlternatives(campaign.subject, body, settings.DEFAULT_FROM_EMAIL, [delivery.recipient], headers=headers)
        message.attach_alternative(email_html(campaign.subject, html, action_url=origin, action_label='Visit the community'), 'text/html')
        if message.send(fail_silently=False) != 1:
            raise RuntimeError('The email backend did not accept the message.')
        accepted = True
        MemberEmailDelivery.objects.filter(pk=delivery.pk).update(status=mode, sent_at=timezone.now(), last_error='', updated_at=timezone.now())
        finish_campaign(campaign.pk)
        return True
    except Exception as exc:
        if accepted:
            # Never automatically retry after SMTP accepted the email. A database
            # outage leaves a sending claim for explicit, duplicate-aware recovery.
            logger.warning('Member email delivery %s was accepted but recording completion failed (%s)', delivery.pk, type(exc).__name__)
            return True
        # SMTP/provider exception text can contain credentials; keep only its class.
        MemberEmailDelivery.objects.filter(pk=delivery.pk).update(
            status='failed', last_error=f'{type(exc).__name__}: member email delivery failed; check configuration.',
            next_attempt_at=timezone.now() + timedelta(minutes=2 ** min(delivery.attempts, 10)), updated_at=timezone.now(),
        )
        logger.warning('Member email delivery %s failed (%s)', delivery.pk, type(exc).__name__)
        return False


def discover_automatic_campaigns(limit=100, now=None):
    """Discover publications after explicit activation; unique source keys stop resends."""
    if not getattr(settings, 'MEMBER_EMAIL_ENABLED', False):
        return 0
    config = MemberEmailSettings.objects.filter(pk=1).first()
    if not config:
        return 0
    origin = public_origin()
    now = now or timezone.now()
    count = 0
    if config.automatic_blog and config.blog_enabled_since:
        from platform_api.models import BlogPost
        existing = MemberEmailCampaign.objects.filter(source_key__startswith='blog:').values_list('source_key', flat=True)
        seen = {int(value.split(':')[1]) for value in existing}
        posts = BlogPost.objects.filter(status='published', published_at__gte=config.blog_enabled_since, published_at__lte=now).exclude(pk__in=seen).order_by('published_at', 'pk')[:limit]
        for post in posts:
            _, created = MemberEmailCampaign.objects.get_or_create(source_key=f'blog:{post.pk}', defaults={
                'topic': 'blog_updates', 'subject': f'New article: {post.title}'[:180].replace('\r', ' ').replace('\n', ' '),
                'body': f'{post.title}\n\n{strip_tags(post.excerpt)[:1500]}\n\nRead the article: {origin}/blog/{quote(post.slug, safe="")}',
                'status': 'scheduled', 'scheduled_at': now,
            })
            count += int(created)
    if config.automatic_shop and config.shop_enabled_since:
        from shop.models import Product
        existing = MemberEmailCampaign.objects.filter(source_key__startswith='shop:').values_list('source_key', flat=True)
        seen = {int(value.split(':')[1]) for value in existing}
        products = Product.objects.filter(is_active=True, created_at__gte=config.shop_enabled_since, created_at__lte=now).exclude(ecommerce_platform='amazon').exclude(pk__in=seen).order_by('created_at', 'pk')[:limit]
        for product in products:
            _, created = MemberEmailCampaign.objects.get_or_create(source_key=f'shop:{product.pk}', defaults={
                'topic': 'shop_updates', 'subject': f'New in the shop: {product.name}'[:180].replace('\r', ' ').replace('\n', ' '),
                'body': f'{product.name}\n\n{strip_tags(product.description)[:1500]}\n\nExplore the shop: {origin}/store',
                'status': 'scheduled', 'scheduled_at': now,
            })
            count += int(created)
    return count
