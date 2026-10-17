"""Server-owned provider credentials and validation against an approved channel.

No access token, metric value, owner ID or channel ID comes from a website form.
"""
import json
from pathlib import Path

from django.conf import settings


class ProviderSetupRequired(ValueError):
    pass


def channel_credentials(application):
    filename = getattr(settings, 'LEAGUE_PROVIDER_CREDENTIALS_FILE', '')
    if not filename:
        return {}
    try:
        document = json.loads(Path(filename).read_text(encoding='utf-8'))
        data = document.get(str(application.pk), {})
        if not isinstance(data, dict) or data.get('user_id') != application.user_id:
            return {}
        return data
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ProviderSetupRequired('League provider configuration needs administrator attention.') from exc


def approved_channel_context(application):
    """Resolve one trusted provider binding for a bounded collection batch."""
    from .providers import resolve_youtube_channel, TikTokCredential
    if application.status != 'accepted' or not application.channel_verified or application.removal_requested:
        raise ProviderSetupRequired('An approved, verified channel is required.')
    platform = application.channel_type
    credential_data = channel_credentials(application)
    credential = None
    if platform == 'tiktok':
        if not credential_data.get('access_token') or not credential_data.get('open_id'):
            raise ProviderSetupRequired('This TikTok channel needs an authorized provider connection before league entry.')
        credential = TikTokCredential(
            access_token=credential_data['access_token'], expected_open_id=credential_data['open_id'],
        )
        approved_channel = credential.expected_open_id
    elif platform == 'youtube':
        approved_channel = resolve_youtube_channel(application.channel_link)
    else:
        raise ProviderSetupRequired('This approved channel platform is unsupported.')
    return platform, credential, approved_channel, credential_data


def fetch_verified_video_id(application, video_id, *, context=None):
    """Fetch a provider-discovered ID using server-owned channel context only."""
    from .providers import fetch_video, require_channel
    platform, credential, approved_channel, credential_data = context or approved_channel_context(application)
    data = fetch_video(platform, video_id, credential=credential)
    require_channel(data, approved_channel)
    # Classification, if the provider cannot establish it, is an explicit
    # server-reviewed per-video value; users cannot submit their own format.
    formats = credential_data.get('reviewed_formats', {})
    if isinstance(formats, dict) and video_id in formats:
        reviewed = formats[video_id]
        if isinstance(reviewed, str) and reviewed.strip() == reviewed and reviewed and len(reviewed) <= 32:
            data['video_format'] = reviewed
    # Administrators may link known cross-posts/reuploads to one underlying edit.
    # This mapping is server-owned; never accept a browser-supplied content key.
    content_keys = credential_data.get('reviewed_content_keys', {})
    if isinstance(content_keys, dict) and video_id in content_keys:
        reviewed_key = content_keys[video_id]
        if not isinstance(reviewed_key, str) or not reviewed_key.strip() or len(reviewed_key) > 240:
            raise ProviderSetupRequired('The reviewed edit identity needs administrator attention.')
        data['content_key'] = 'reviewed:' + reviewed_key.strip()
    data['platform'] = platform
    data['video_id'] = video_id
    # Keep the provider's canonical author URL. TikTok handles in a pasted URL
    # are not proof of ownership and must not replace the authorized share URL.
    return data


def fetch_verified_video(application, video_url):
    from .providers import canonical_video
    platform, video_id, _ = canonical_video(video_url)
    if application.channel_type != platform:
        raise ProviderSetupRequired('Choose the approved channel for this video platform.')
    return fetch_verified_video_id(application, video_id)
