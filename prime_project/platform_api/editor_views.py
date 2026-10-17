"""V2 editor onboarding using the existing applications and approval signals."""
import logging
import re
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.api_views import limited
from core.validators import MAX_CHANNEL_SCREENSHOT_SIZE_MB
from edithub.forms import EditorApplicationForm
from edithub.application_policy import active_application, SINGLE_CHANNEL_MESSAGE
from edithub.models import EditorApplication
from edithub.utils import fetch_tiktok_channel_data, fetch_youtube_channel_data
from .views import endpoint, image_url, payload

logger = logging.getLogger(__name__)


def application_data(item):
    return {
        'id': item.pk, 'platform': item.channel_type, 'channel_link': item.channel_link,
        'channel_name': item.channel_name, 'channel_thumbnail': item.channel_thumbnail,
        'channel_screenshot': image_url(item.channel_screenshot),
        'editing_area': item.editing_area, 'editing_area_label': item.get_editing_area_display(),
        'editing_area_other': item.editing_area_other,
        'editing_tool': item.editing_tool, 'editing_tool_label': item.get_editing_tool_display(),
        'status': item.status, 'channel_verified': item.channel_verified,
        'removal_requested': item.removal_requested, 'applied_at': item.applied_date,
        'reviewed_at': item.reviewed_date,
        'can_confirm': item.status in {'pending', 'accepted'} and not item.channel_verified and not item.removal_requested,
        'can_remove': item.status == 'accepted' and not item.removal_requested,
        'url': f'/applications/editors/{item.pk}',
    }


def conflict(item, message):
    return JsonResponse({'error': message, 'application': application_data(item)}, status=409)


def existing_application(user, link):
    own = EditorApplication.objects.filter(user=user)
    return active_application(user) or own.filter(channel_link=link).first()


def channel_url(value, platform):
    """Only pass actual profile URLs to the established provider lookups."""
    url = urlsplit(value)
    hosts = {'youtube': {'youtube.com', 'www.youtube.com', 'm.youtube.com'},
             'tiktok': {'tiktok.com', 'www.tiktok.com'}}
    pattern = r'/(?:@[\w.-]+|(?:channel|c|user)/[\w.-]+)/?' if platform == 'youtube' else r'/@[\w.]+/?'
    if (url.scheme not in {'http', 'https'} or url.hostname not in hosts.get(platform, set())
            or url.username or url.password or url.port or not re.fullmatch(pattern, url.path, re.ASCII)):
        raise ValueError('Use a YouTube or TikTok channel profile URL, not a video link.')
    return f'https://www.{platform}.com{url.path.rstrip("/")}'


@endpoint(('GET', 'POST'), authenticated=True)
def applications(request):
    if request.method == 'GET':
        choices = lambda values: [{'value': value, 'label': label} for value, label in values]
        return JsonResponse({
            'results': [application_data(item) for item in EditorApplication.objects.filter(user=request.user).order_by('-applied_date', '-pk')],
            'can_apply': request.user.role == 'user',
            'platforms': choices(EditorApplication.CHANNEL_TYPE_CHOICES),
            'editing_areas': choices(EditorApplication.EDITING_AREA_CHOICES),
            'editing_tools': choices(EditorApplication.EDITING_TOOL_CHOICES),
            'max_screenshot_mb': MAX_CHANNEL_SCREENSHOT_SIZE_MB,
        })
    if request.user.role != 'user':
        return JsonResponse({'error': 'Use a normal member account to apply as an editor.'}, status=403)
    if request.content_type != 'multipart/form-data':
        return JsonResponse({'error': 'Submit the form with a channel screenshot.'}, status=400)
    if limited(request, 'editor-application', limit=12, identity=str(request.user.pk)):
        return JsonResponse({'error': 'Too many attempts. Please try again in a few minutes.'}, status=429)
    data = request.POST.copy()
    data['channel_verified'] = ''  # Only the separate confirmation step may set this.
    try:
        data['channel_link'] = channel_url(data.get('channel_link', '').strip(), data.get('channel_type'))
    except ValueError:
        return JsonResponse({'error': 'Check your channel link.', 'errors': {'channel_link': [
            'Use the selected platform’s channel profile URL, such as https://www.youtube.com/@yourchannel or https://www.tiktok.com/@yourchannel.',
        ]}}, status=400)
    form = EditorApplicationForm(data=data, files=request.FILES)
    if not form.is_valid():
        return JsonResponse({'error': 'Please check the application fields.', 'errors': form.errors.get_json_data()}, status=400)
    platform, link = form.cleaned_data['channel_type'], form.cleaned_data['channel_link']
    existing = existing_application(request.user, link)
    if existing:
        return conflict(existing, SINGLE_CHANNEL_MESSAGE)
    try:
        channel = (fetch_youtube_channel_data if platform == 'youtube' else fetch_tiktok_channel_data)(link)
    except Exception:
        logger.warning('Editor channel lookup failed for %s', platform)
        return JsonResponse({'error': 'Channel lookup is temporarily unavailable. Your application was not created; please try again.'}, status=503)
    if not channel.get('channel_name') or (channel.get('error') and platform != 'tiktok'):
        if platform == 'youtube':
            code = channel.get('error_code', 'provider_unavailable')
            messages = {
                'configuration_error': 'YouTube channel lookup is not configured correctly on our website. Please contact us; changing your channel link will not fix this.',
                'quota_exceeded': 'Our YouTube lookup limit has been reached. Please try again later. Your application was not created.',
                'channel_not_found': 'YouTube could not find this channel. Check that the handle is correct and the channel is public.',
                'provider_unavailable': 'YouTube channel lookup is temporarily unavailable. Please try again later. Your application was not created.',
            }
            return JsonResponse({'error': messages.get(code, messages['provider_unavailable']),
                                 'code': code if code in messages else 'provider_unavailable'},
                                status=400 if code == 'channel_not_found' else 503)
        return JsonResponse({'error': 'We could not load that channel. Check that it is public and the link is correct, then try again. If this continues, contact us.'}, status=503)
    application = form.save(commit=False)
    application.user = request.user
    application.channel_name = str(channel['channel_name'])[:200]
    application.channel_thumbnail = str(channel.get('thumbnail') or '')[:500]
    # Retained for legacy compatibility only; never exposed as V2 rank or points.
    application.follower_count = channel.get('subscriber_count') or channel.get('follower_count') or 0
    application.status = 'pending'
    application.channel_verified = False
    try:
        with transaction.atomic():
            # Serialize this member's V2 requests to avoid two active applications.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            existing = existing_application(request.user, link)
            if existing:
                return conflict(existing, SINGLE_CHANNEL_MESSAGE)
            application.save()
    except IntegrityError:
        if application.channel_screenshot and application.channel_screenshot._committed:
            application.channel_screenshot.delete(save=False)
        return JsonResponse({'error': 'This channel already has an application. Refresh Your applications.'}, status=409)
    return JsonResponse({'application': application_data(application)}, status=201)


@endpoint(authenticated=True)
def detail(request, application_id):
    item = get_object_or_404(EditorApplication, pk=application_id, user=request.user)
    return JsonResponse({'application': application_data(item)})


@endpoint(('POST',), authenticated=True)
def action(request, application_id, operation):
    data = payload(request)
    if request.user.role != 'user':
        return JsonResponse({'error': 'Only the member can manage their application.'}, status=403)
    with transaction.atomic():
        item = get_object_or_404(EditorApplication.objects.select_for_update(), pk=application_id, user=request.user)
        if operation == 'confirm':
            if item.status not in {'pending', 'accepted'} or item.removal_requested:
                return conflict(item, 'This application is no longer awaiting confirmation.')
            if data.get('owns_channel') is not True:
                return JsonResponse({'error': 'Confirm that this is your channel before submitting.'}, status=400)
            if not item.channel_verified:
                if not item.data_consent or not item.channel_screenshot:
                    return conflict(item, 'This approved application is missing consent or an ownership screenshot. Contact the team to complete the record.' if item.status == 'accepted' else 'This application is missing consent or a screenshot. Cancel it and apply again.')
                item.channel_verified = True
                # Existing signal queues the administrator alert only on this transition.
                item.save(update_fields=['channel_verified', 'updated_date'])
        elif operation == 'cancel':
            if item.status != 'pending' or item.channel_verified or item.removal_requested:
                return conflict(item, 'Only an unconfirmed application can be cancelled here.')
            item.delete()
            return JsonResponse({'message': 'Unconfirmed application cancelled. You can apply again.'})
        elif operation == 'remove':
            if item.status != 'accepted':
                return conflict(item, 'Only approved editors can request removal.')
            if not item.removal_requested:
                item.removal_requested = True
                item.removal_requested_date = timezone.now()
                item.save(update_fields=['removal_requested', 'removal_requested_date', 'updated_date'])
        else:
            return JsonResponse({'error': 'Unknown action.'}, status=404)
    return JsonResponse({'application': application_data(item)})
