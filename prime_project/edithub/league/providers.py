"""Official league metric adapters; no scraping, inferred history, or zero fallbacks.

Callers own eligibility, approved identity bindings, credential storage, retries,
format review, retention and scoring. Never build a TikTokCredential from browser
input: expected_open_id must come from that editor's verified server-side link.
The module deliberately does not read a global TikTok access token.

API references (checked September 2026):
https://developers.google.com/youtube/v3/docs/videos
https://developers.google.com/youtube/v3/docs/channels/list
https://developers.tiktok.com/docs/en/tiktok-api-v2-video-query
https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, unquote, urlsplit

import requests


YOUTUBE_VIDEO = re.compile(r'^[A-Za-z0-9_-]{11}$')
YOUTUBE_CHANNEL = re.compile(r'^UC[A-Za-z0-9_-]{22}$')
TIKTOK_VIDEO = re.compile(r'^[1-9][0-9]{9,24}$')
TIKTOK_HANDLE = re.compile(r'^[A-Za-z0-9._]{1,24}$')
YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'}
TIKTOK_HOSTS = {'tiktok.com', 'www.tiktok.com', 'm.tiktok.com'}
ENDPOINTS = {
    'youtube_videos': 'https://www.googleapis.com/youtube/v3/videos',
    'youtube_channels': 'https://www.googleapis.com/youtube/v3/channels',
    'youtube_playlist': 'https://www.googleapis.com/youtube/v3/playlistItems',
    'tiktok_user': 'https://open.tiktokapis.com/v2/user/info/',
    'tiktok_query': 'https://open.tiktokapis.com/v2/video/query/',
    'tiktok_list': 'https://open.tiktokapis.com/v2/video/list/',
}
MAX_COUNTER = 2**63 - 1


def utc_now():
    return datetime.now(timezone.utc)


class ProviderError(ValueError):
    """A safe, credential-free error; callers must store missing counters as null."""

    def __init__(self, code, message, *, retryable=False, requested_at=None, completed_at=None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.requested_at = requested_at
        self.completed_at = completed_at or utc_now()
        self.status = 'unavailable'


@dataclass(frozen=True)
class TikTokCredential:
    access_token: str = field(repr=False)
    expected_open_id: str


def _url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ProviderError('invalid_url', 'Use a supported public video or channel URL.')
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port is not None:
            raise ValueError
        if not parsed.hostname or parsed.hostname.endswith('.'):
            raise ValueError
        return parsed
    except ValueError:
        raise ProviderError('invalid_url', 'Use a supported public video or channel URL.') from None


def _video_id(platform, video_id):
    pattern = {'youtube': YOUTUBE_VIDEO, 'tiktok': TIKTOK_VIDEO}.get(platform)
    if pattern is None or not isinstance(video_id, str) or not pattern.fullmatch(video_id):
        raise ProviderError('invalid_video', 'Unsupported platform or invalid video ID.')
    return video_id


def canonical_video(url):
    """Normalize URL variants without fetching URLs or following short-link redirects."""
    parsed = _url(url)
    host = parsed.hostname.lower()
    path = parsed.path.rstrip('/')
    if host in YOUTUBE_HOSTS | {'youtu.be', 'www.youtu.be', 'www.youtube-nocookie.com', 'youtube-nocookie.com'}:
        if host in {'youtu.be', 'www.youtu.be'}:
            video_id = path.removeprefix('/')
        elif path == '/watch' and host in YOUTUBE_HOSTS:
            try:
                values = parse_qs(parsed.query, max_num_fields=30).get('v', [])
            except ValueError:
                values = []
            if len(values) != 1:
                raise ProviderError('invalid_video', 'The YouTube URL must identify one video.')
            video_id = values[0]
        else:
            match = re.fullmatch(r'/(?:shorts|embed|live)/([^/]+)', path)
            if not match:
                raise ProviderError('invalid_video', 'Use a direct YouTube video URL.')
            video_id = match.group(1)
        _video_id('youtube', video_id)
        return 'youtube', video_id, f'https://www.youtube.com/watch?v={video_id}'
    if host in TIKTOK_HOSTS:
        match = re.fullmatch(r'/@([A-Za-z0-9._]{1,24})/video/([0-9]+)', path)
        if not match:
            raise ProviderError('invalid_video', 'Use the full TikTok @creator/video URL, not a short link.')
        handle, video_id = match.groups()
        _video_id('tiktok', video_id)
        return 'tiktok', video_id, f'https://www.tiktok.com/@{handle}/video/{video_id}'
    raise ProviderError('unsupported_url', 'Only direct YouTube and TikTok video URLs are supported.')


def _youtube_key(credential):
    if credential is None:
        # YouTube public data uses the application's API key. It is never a
        # substitute for another creator's private OAuth authorization.
        from django.conf import settings
        credential = (getattr(settings, 'LEAGUE_YOUTUBE_API_KEY', '') or getattr(settings, 'YOUTUBE_API_KEY', '')) if settings.configured else ''
    if not isinstance(credential, str) or not credential.strip():
        raise ProviderError('not_configured', 'YouTube metric access is not configured.')
    return credential.strip()


def _tiktok_credential(credential):
    if not isinstance(credential, TikTokCredential):
        raise ProviderError('authorization_required', 'This editor must authorize TikTok video access.')
    if not isinstance(credential.access_token, str) or not credential.access_token or any(c.isspace() for c in credential.access_token):
        raise ProviderError('authorization_required', 'This editor must authorize TikTok video access.')
    if not isinstance(credential.expected_open_id, str) or not credential.expected_open_id or len(credential.expected_open_id) > 255:
        raise ProviderError('identity_required', 'A verified TikTok identity is required.')
    return credential


def _request(endpoint, *, method='GET', params=None, headers=None, body=None):
    started = utc_now()
    try:
        # Endpoints are constants, never user-supplied URLs. Redirects are denied
        # so a provider/proxy redirect cannot forward credentials elsewhere.
        url = ENDPOINTS[endpoint]
        kwargs = {'params': params or {}, 'headers': headers or {}, 'timeout': (3.05, 10), 'allow_redirects': False}
        response = requests.get(url, **kwargs) if method == 'GET' else requests.post(url, json=body, **kwargs)
        if response.status_code != 200:
            raise ProviderError(
                'rate_limited' if response.status_code == 429 else 'provider_unavailable',
                'The provider did not return an eligible response.',
                retryable=response.status_code == 429 or response.status_code >= 500,
                requested_at=started,
            )
        payload = response.json()
        completed = utc_now()
        if not isinstance(payload, dict):
            raise ProviderError('invalid_response', 'The provider returned invalid data.', requested_at=started, completed_at=completed)
        return payload, started, completed
    except requests.RequestException:
        # requests exception strings may include an API key in the request URL.
        raise ProviderError('provider_unavailable', 'The provider request could not complete.', retryable=True, requested_at=started) from None
    except (ValueError, TypeError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError('invalid_response', 'The provider returned invalid data.', requested_at=started) from None


def _counter(value, field_name):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'[0-9]+', str(value)):
        raise ProviderError('missing_metrics', f'The provider did not return a valid {field_name}.')
    value = int(value)
    if value > MAX_COUNTER:
        raise ProviderError('invalid_metrics', f'The provider returned an unsupported {field_name}.')
    return value


def _text(value, field_name, max_length=2000):
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ProviderError('invalid_response', f'The provider did not return a valid {field_name}.')
    return value


def _published(value, completed, *, unix=False):
    try:
        if unix:
            value = datetime.fromtimestamp(_counter(value, 'publication timestamp'), timezone.utc)
        else:
            value = datetime.fromisoformat(_text(value, 'publication timestamp', 60).replace('Z', '+00:00'))
        if value.tzinfo is None or value.utcoffset() is None or value > completed:
            raise ValueError
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise ProviderError('invalid_publication', 'The provider did not return a valid publication time.') from None


def _items(payload):
    if payload.get('error') or not isinstance(payload.get('items'), list):
        raise ProviderError('provider_unavailable', 'YouTube data is unavailable for this request.')
    return payload['items']


def _tiktok_data(payload):
    error = payload.get('error')
    if not isinstance(error, dict) or error.get('code') != 'ok' or not isinstance(payload.get('data'), dict):
        raise ProviderError('provider_unavailable', 'TikTok data or permission is unavailable for this request.')
    return payload['data']


def resolve_youtube_channel(channel_link, credential=None):
    """Resolve a reviewed channel link exactly; never search by display name."""
    parsed = _url(channel_link)
    if parsed.hostname.lower() not in YOUTUBE_HOSTS:
        raise ProviderError('invalid_channel', 'Use a YouTube channel ID, handle or legacy username URL.')
    segments = [unquote(part) for part in parsed.path.strip('/').split('/')]
    # Channel tab suffixes identify the same channel; arbitrary path tails do not.
    if segments[-1] in {'videos', 'shorts', 'featured', 'streams', 'about'}:
        segments.pop()
    params = {'part': 'id', 'key': _youtube_key(credential)}
    if len(segments) == 2 and segments[0] == 'channel' and YOUTUBE_CHANNEL.fullmatch(segments[1]):
        params['id'] = segments[1]
    elif len(segments) == 1 and segments[0].startswith('@') and 1 < len(segments[0]) <= 100 and not any(c.isspace() or c in '/\\?#' for c in segments[0]):
        params['forHandle'] = segments[0]
    elif len(segments) == 2 and segments[0] == 'user' and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', segments[1]):
        params['forUsername'] = segments[1]
    else:
        raise ProviderError('invalid_channel', 'A /channel/ID, /@handle or /user/name URL is required; custom /c/ URLs cannot be resolved safely.')
    payload, _, _ = _request('youtube_channels', params=params)
    items = _items(payload)
    if len(items) != 1 or not isinstance(items[0], dict) or not YOUTUBE_CHANNEL.fullmatch(str(items[0].get('id', ''))):
        raise ProviderError('channel_unavailable', 'The approved YouTube channel could not be resolved.')
    channel_id = items[0]['id']
    if 'id' in params and channel_id != params['id']:
        raise ProviderError('identity_mismatch', 'The returned channel identity does not match.')
    return channel_id


def _tiktok_identity(credential):
    credential = _tiktok_credential(credential)
    headers = {'Authorization': 'Bearer ' + credential.access_token}
    payload, started, _ = _request('tiktok_user', params={'fields': 'open_id'}, headers=headers)
    user = _tiktok_data(payload).get('user')
    if not isinstance(user, dict) or user.get('open_id') != credential.expected_open_id:
        raise ProviderError('identity_mismatch', 'TikTok authorization does not match this editor.', requested_at=started)
    return headers, started


def _fetch_youtube(video_id, credential):
    payload, started, completed = _request('youtube_videos', params={
        'part': 'snippet,statistics,status,contentDetails', 'id': video_id, 'key': _youtube_key(credential),
    })
    items = _items(payload)
    if len(items) != 1 or not isinstance(items[0], dict) or items[0].get('id') != video_id:
        raise ProviderError('video_unavailable', 'This YouTube video is unavailable.')
    item = items[0]
    snippet, statistics, status = (item.get(key) for key in ('snippet', 'statistics', 'status'))
    if not all(isinstance(part, dict) for part in (snippet, statistics, status)):
        raise ProviderError('invalid_response', 'Required YouTube video data is missing.')
    if status.get('privacyStatus') != 'public' or status.get('uploadStatus') != 'processed' or snippet.get('liveBroadcastContent') != 'none':
        raise ProviderError('video_ineligible', 'Only public, processed, non-live YouTube videos are eligible.')
    channel_id = snippet.get('channelId')
    if not isinstance(channel_id, str) or not YOUTUBE_CHANNEL.fullmatch(channel_id):
        raise ProviderError('invalid_response', 'The video has no valid channel identity.')
    return {
        'platform': 'youtube', 'video_id': video_id, 'canonical_url': f'https://www.youtube.com/watch?v={video_id}',
        'channel_id': channel_id, 'title': _text(snippet.get('title'), 'title'),
        'likes': _counter(statistics.get('likeCount'), 'like count'),
        'views': _counter(statistics.get('viewCount'), 'view count'),
        'published_at': _published(snippet.get('publishedAt'), completed),
        # Public Data API does not reliably identify Shorts. A short URL or a
        # short duration is not a classification proof. Scoring needs review.
        'video_format': 'unknown', 'format': 'unknown',
        'requested_at': started, 'completed_at': completed, 'observed_at': completed,
        'status': 'success', 'provider': 'youtube_data_v3',
        'provenance': {'endpoint': ENDPOINTS['youtube_videos'], 'method': 'videos.list',
                       'counter_scope': 'lifetime', 'format_source': 'not_exposed_by_public_api',
                       'timestamp_source': 'server_response_completion'},
    }


def _fetch_tiktok(video_id, credential):
    headers, started = _tiktok_identity(credential)
    payload, _, completed = _request('tiktok_query', method='POST', headers=headers,
        params={'fields': 'id,create_time,share_url,title,like_count,view_count'},
        body={'filters': {'video_ids': [video_id]}},
    )
    videos = _tiktok_data(payload).get('videos')
    if not isinstance(videos, list) or len(videos) != 1 or not isinstance(videos[0], dict) or videos[0].get('id') != video_id:
        raise ProviderError('video_unavailable', 'This TikTok video is unavailable to its authorized creator.')
    video = videos[0]
    platform, returned_id, canonical_url = canonical_video(video.get('share_url'))
    if platform != 'tiktok' or returned_id != video_id:
        raise ProviderError('identity_mismatch', 'The returned TikTok video identity does not match.')
    return {
        'platform': 'tiktok', 'video_id': video_id, 'canonical_url': canonical_url,
        'channel_id': credential.expected_open_id, 'title': _text(video.get('title'), 'title'),
        'likes': _counter(video.get('like_count'), 'like count'),
        'views': _counter(video.get('view_count'), 'view count'),
        'published_at': _published(video.get('create_time'), completed, unix=True),
        'video_format': 'video', 'format': 'video',
        'requested_at': started, 'completed_at': completed, 'observed_at': completed,
        'status': 'success', 'provider': 'tiktok_display_v2',
        'provenance': {'endpoint': ENDPOINTS['tiktok_query'], 'method': 'video.query',
                       'counter_scope': 'lifetime', 'ownership': 'authorized_open_id_and_video_query',
                       'format_source': 'tiktok_video_resource', 'timestamp_source': 'server_response_completion'},
    }


def fetch_video(platform, video_id, credential=None):
    """Return one validated lifetime observation; failures never become zeroes.

    TikTok requires a per-editor TikTokCredential from trusted server storage.
    YouTube accepts an API key string, then LEAGUE_YOUTUBE_API_KEY, then
    YOUTUBE_API_KEY. This also supports the local V2 settings without Docker.
    Completion times are real UTC response times, never caller-supplied cutoffs.
    """
    _video_id(platform, video_id)
    started = utc_now()
    try:
        return _fetch_youtube(video_id, credential) if platform == 'youtube' else _fetch_tiktok(video_id, credential)
    except ProviderError as exc:
        if exc.requested_at is None:
            exc.requested_at = started
        raise


def require_channel(observation, expected_channel_id):
    """Check an observation against an existing verified server-side identity."""
    if not expected_channel_id or observation.get('channel_id') != expected_channel_id:
        raise ProviderError('identity_mismatch', 'The video does not belong to the approved channel.')
    return observation


def list_channel_video_ids(platform, channel_id, credential=None, *, limit=20, cursor=None):
    """Discover comparison candidates through supported APIs, not past metrics.

    Returns {video_ids, cursor, has_more}. Call fetch_video for each candidate;
    observations collected now cannot be backdated into an earlier baseline.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= (50 if platform == 'youtube' else 20):
        raise ProviderError('invalid_limit', 'Use a supported comparison batch size.')
    if platform == 'youtube':
        if not isinstance(channel_id, str) or not YOUTUBE_CHANNEL.fullmatch(channel_id):
            raise ProviderError('invalid_channel', 'A canonical YouTube channel ID is required.')
        key = _youtube_key(credential)
        payload, _, _ = _request('youtube_channels', params={'part': 'contentDetails', 'id': channel_id, 'key': key})
        items = _items(payload)
        if len(items) != 1 or not isinstance(items[0], dict) or items[0].get('id') != channel_id:
            raise ProviderError('channel_unavailable', 'The YouTube channel is unavailable.')
        try:
            playlist_id = _text(items[0]['contentDetails']['relatedPlaylists']['uploads'], 'uploads playlist', 100)
        except (KeyError, TypeError):
            raise ProviderError('invalid_response', 'The uploads playlist is unavailable.') from None
        params = {'part': 'contentDetails', 'playlistId': playlist_id, 'maxResults': limit, 'key': key}
        if cursor is not None:
            params['pageToken'] = _text(cursor, 'page cursor', 1000)
        payload, _, _ = _request('youtube_playlist', params=params)
        videos = _items(payload)
        try:
            ids = [_video_id(platform, item['contentDetails']['videoId']) for item in videos]
        except (KeyError, TypeError):
            raise ProviderError('invalid_response', 'The comparison list contains an invalid video.') from None
        next_cursor = payload.get('nextPageToken')
        if next_cursor is not None:
            _text(next_cursor, 'page cursor', 1000)
    elif platform == 'tiktok':
        credential = _tiktok_credential(credential)
        if channel_id != credential.expected_open_id:
            raise ProviderError('identity_mismatch', 'The comparison creator does not match this authorization.')
        headers, _ = _tiktok_identity(credential)
        body = {'max_count': limit}
        if cursor is not None:
            body['cursor'] = _counter(cursor, 'page cursor')
        payload, _, _ = _request('tiktok_list', method='POST', headers=headers, params={'fields': 'id'}, body=body)
        data = _tiktok_data(payload)
        if not isinstance(data.get('videos'), list) or not isinstance(data.get('has_more'), bool):
            raise ProviderError('invalid_response', 'The comparison list is unavailable.')
        try:
            ids = [_video_id(platform, item['id']) for item in data['videos']]
        except (KeyError, TypeError):
            raise ProviderError('invalid_response', 'The comparison list contains an invalid video.') from None
        next_cursor = _counter(data.get('cursor'), 'page cursor') if data['has_more'] else None
    else:
        raise ProviderError('unsupported_platform', 'Unsupported comparison platform.')
    if len(ids) > limit or len(set(ids)) != len(ids):
        raise ProviderError('invalid_response', 'The comparison list contains duplicate or excessive videos.')
    return {'video_ids': ids, 'cursor': next_cursor, 'has_more': next_cursor is not None}
