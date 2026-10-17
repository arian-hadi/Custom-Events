"""Read-only YouTube metadata and owner-authorized caption access.

Input URLs are parsed locally; only fixed Google/YouTube endpoints are contacted.
Provider messages, request URLs and credentials must never reach admin notices.
"""

import html
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware


API_ROOT = 'https://www.googleapis.com/youtube/v3/'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
TIMEOUT = (5, 20)
MAX_TRANSCRIPT_BYTES = 1024 * 1024
MAX_CHANNEL_PAGE_BYTES = 4 * 1024 * 1024
_CHANNEL_ID = re.compile(r'UC[A-Za-z0-9_-]{22}\Z')
_VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}\Z')
_PLAYLIST_ID = re.compile(r'[A-Za-z0-9_-]{10,100}\Z')
_YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com'}
_TIME_LINE = re.compile(r'^\s*(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3}\s*-->\s*(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3}(?:\s.*)?$')


class ProviderError(Exception):
    """A safe, actionable message for an admin, without upstream secrets."""


def _invalid_response():
    return ProviderError('YouTube returned incomplete or invalid data. Please try again later.')


def _youtube_url(value, *, allow_short=False):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ProviderError('Enter a complete YouTube URL.')
    value = value.strip()
    if re.search(r'[\x00-\x20\x7f\\]', value):
        raise ProviderError('Enter a valid YouTube URL without spaces.')
    try:
        parsed = urlsplit(value)
        hosts = _YOUTUBE_HOSTS | ({'youtu.be', 'www.youtu.be'} if allow_short else set())
        if (parsed.scheme not in {'http', 'https'} or parsed.hostname not in hosts
                or parsed.username or parsed.password or parsed.port is not None):
            raise ValueError
        path = unquote(parsed.path)
        if re.search(r'[\x00-\x20\x7f\\]', path):
            raise ValueError
    except (ValueError, UnicodeError):
        raise ProviderError('Use a link from youtube.com' + (' or youtu.be.' if allow_short else '.')) from None
    return parsed, [part for part in path.strip('/').split('/') if part]


def _api_key():
    value = getattr(settings, 'YOUTUBE_API_KEY', '')
    if not isinstance(value, str) or not value.strip():
        raise ProviderError('Configure YOUTUBE_API_KEY before checking your YouTube channel.')
    return value.strip()


def _status_error(response, *, captions=False, oauth=False):
    if response.status_code == 200:
        return
    if oauth:
        raise ProviderError('YouTube authorization could not be refreshed. Reconnect the channel owner with the youtube.force-ssl scope and update the credential file.')
    # Inspect only known reason codes; never show arbitrary provider text.
    reasons = set()
    try:
        payload = response.json()
        error = payload.get('error', {}) if isinstance(payload, dict) else {}
        errors = error.get('errors', []) if isinstance(error, dict) else []
        reasons = {item.get('reason') for item in errors if isinstance(item, dict) and isinstance(item.get('reason'), str)}
    except (ValueError, TypeError):
        pass
    if response.status_code == 429 or reasons.intersection({'quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded'}):
        raise ProviderError('The YouTube API quota or rate limit has been reached. Try again after the quota resets.')
    if captions and response.status_code in {401, 403}:
        raise ProviderError('YouTube caption access was denied. Authorize an account that can edit this video with the youtube.force-ssl scope, or upload the script manually.')
    if captions and response.status_code == 404:
        raise ProviderError('This YouTube caption track is no longer available. Refresh the video or upload the script manually.')
    if response.status_code in {400, 401, 403}:
        raise ProviderError('YouTube rejected the API request. Check that the YouTube Data API is enabled and the API credentials and restrictions allow this server.')
    if response.status_code == 404:
        raise ProviderError('This YouTube channel, video or uploads playlist could not be found. Check that it is public and the URL is correct.')
    raise ProviderError('YouTube is unavailable right now. Please try again later.')


def _json_request(url, *, params=None, headers=None, data=None, captions=False, oauth=False):
    response = None
    try:
        if data is None:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        else:
            response = requests.post(url, data=data, timeout=TIMEOUT, allow_redirects=False)
        _status_error(response, captions=captions, oauth=oauth)
        payload = response.json()
        if not isinstance(payload, dict):
            raise _invalid_response()
        return payload
    except requests.RequestException:
        raise ProviderError('Could not connect to YouTube. Please try again later.') from None
    except (ValueError, TypeError):
        raise _invalid_response() from None
    finally:
        if response is not None:
            response.close()


def _items(payload):
    items = payload.get('items')
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise _invalid_response()
    return items


def resolve_channel(channel_url):
    """Return channel_id, title and uploads_playlist_id for a public channel."""
    _, parts = _youtube_url(channel_url)
    if parts and parts[0] == 'c':
        raise ProviderError('Legacy /c/ channel links are not supported. Copy the channel\'s current /@handle or /channel/UC… URL from YouTube.')
    tabs = {'videos', 'shorts', 'streams', 'featured', 'about', 'playlists', 'community'}
    selector = {}
    if parts and parts[0].startswith('@') and len(parts[0]) > 1:
        if len(parts) > 2 or (len(parts) == 2 and parts[1] not in tabs):
            raise ProviderError('Use your YouTube channel URL, not a video or playlist URL.')
        selector['forHandle'] = parts[0]
    elif len(parts) in {2, 3} and parts[0] in {'channel', 'user'} and (len(parts) == 2 or parts[2] in tabs):
        if parts[0] == 'channel':
            if not _CHANNEL_ID.fullmatch(parts[1]):
                raise ProviderError('The YouTube channel ID is invalid. Copy the full channel URL.')
            selector['id'] = parts[1]
        else:
            selector['forUsername'] = parts[1]
    else:
        raise ProviderError('Use a YouTube channel URL containing /@handle, /channel/UC… or /user/name.')
    items = _items(_json_request(API_ROOT + 'channels', params={
        'part': 'snippet,contentDetails', **selector, 'key': _api_key(),
    }))
    if not items:
        raise ProviderError('No public YouTube channel matched that URL. Check the channel handle and try again.')
    try:
        item = items[0]
        channel_id = item['id']
        title = item['snippet']['title']
        playlist_id = item['contentDetails']['relatedPlaylists']['uploads']
        if (not isinstance(channel_id, str) or not _CHANNEL_ID.fullmatch(channel_id)
                or not isinstance(title, str) or not title.strip()
                or not isinstance(playlist_id, str) or not _PLAYLIST_ID.fullmatch(playlist_id)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise _invalid_response() from None
    return {'channel_id': channel_id, 'title': title, 'uploads_playlist_id': playlist_id}


def _thumbnail(snippet):
    thumbnails = snippet.get('thumbnails', {})
    if not isinstance(thumbnails, dict):
        return ''
    for size in ('maxres', 'standard', 'high', 'medium', 'default'):
        item = thumbnails.get(size, {})
        url = item.get('url', '') if isinstance(item, dict) else ''
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            if (parsed.scheme == 'https' and parsed.hostname in {'i.ytimg.com', 'img.youtube.com'}
                    and parsed.port is None and not parsed.username and not parsed.password):
                return url
        except ValueError:
            continue
    return ''


def _video_metadata(video_id, snippet, published_at):
    try:
        if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id) or not isinstance(snippet, dict):
            raise ValueError
        title, description = snippet['title'], snippet.get('description', '')
        if not isinstance(title, str) or not title.strip() or not isinstance(description, str) or not isinstance(published_at, str):
            raise ValueError
        published = parse_datetime(published_at)
        if published is None or not is_aware(published):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _invalid_response() from None
    return {'video_id': video_id, 'title': title, 'description': description,
            'published_at': published, 'thumbnail_url': _thumbnail(snippet)}


def _videos_tab_error():
    return ProviderError('Could not read the channel\'s Videos tab in Latest order. No uploads were imported. Try again later, or add a video by URL manually.')


def _videos_tab_page(channel_id):
    """Read one public Videos page, without cookies, redirects or pagination."""
    response = None
    try:
        response = requests.get(
            f'https://www.youtube.com/channel/{channel_id}/videos',
            params={'view': '0', 'sort': 'dd', 'flow': 'grid', 'hl': 'en'},
            headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'},
            timeout=TIMEOUT, allow_redirects=False, stream=True,
        )
        if response.status_code != 200:
            raise _videos_tab_error()
        chunks, size, deadline = [], 0, time.monotonic() + 30
        for chunk in response.iter_content(chunk_size=16384):
            size += len(chunk)
            if size > MAX_CHANNEL_PAGE_BYTES or time.monotonic() > deadline:
                raise _videos_tab_error()
            chunks.append(chunk)
        return b''.join(chunks).decode('utf-8')
    except (requests.RequestException, UnicodeError):
        raise _videos_tab_error() from None
    finally:
        if response is not None:
            response.close()


def _latest_video_id(page, channel_id):
    """Use YouTube's tab membership, not duration or thumbnail shape, for Shorts.

    This public page schema is not an official API contract. If it changes or a
    consent/challenge page is returned, fail closed instead of importing uploads.
    Only the first video in the explicitly selected Latest grid is considered.
    """
    try:
        marker = re.search(r'(?:var\s+ytInitialData|window\["ytInitialData"\])\s*=\s*', page)
        if not marker:
            raise ValueError
        data, _ = json.JSONDecoder().raw_decode(page[marker.end():])
        if data['metadata']['channelMetadataRenderer']['externalId'] != channel_id:
            raise ValueError
        tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
        tab = next(item['tabRenderer'] for item in tabs if item.get('tabRenderer', {}).get('selected') is True)
        tab_url = tab['endpoint']['commandMetadata']['webCommandMetadata']['url']
        if not urlsplit(tab_url).path.rstrip('/').endswith('/videos'):
            raise ValueError
        grid = tab['content']['richGridRenderer']
        contents = grid['contents']
        if not isinstance(contents, list):
            raise ValueError
        if not contents:
            return None
        header = grid['header']
        if 'chipBarViewModel' in header:
            chips = [item['chipViewModel'] for item in header['chipBarViewModel']['chips']]
            latest = any(chip.get('selected') is True and chip.get('text') == 'Latest' for chip in chips)
        else:
            chips = [item['chipCloudChipRenderer'] for item in header['feedFilterChipBarRenderer']['contents']]
            latest = any(chip.get('isSelected') is True and chip.get('text', {}).get('simpleText') == 'Latest' for chip in chips)
        if not latest:
            raise ValueError
        for item in contents:
            # Shorts shelves and continuation tokens are not regular videos.
            if 'richSectionRenderer' in item or 'continuationItemRenderer' in item:
                continue
            content = item['richItemRenderer']['content']
            if 'reelItemRenderer' in content or 'shortsLockupViewModel' in content:
                continue
            if 'lockupViewModel' in content:
                video = content['lockupViewModel']
                if video['contentType'] != 'LOCKUP_CONTENT_TYPE_VIDEO':
                    raise ValueError
                video_id = video['contentId']
                endpoint = video['rendererContext']['commandContext']['onTap']['innertubeCommand']
            else:
                video = content['videoRenderer']
                video_id = video['videoId']
                endpoint = video['navigationEndpoint']
            link = urlsplit(endpoint['commandMetadata']['webCommandMetadata']['url'])
            if link.path.startswith('/shorts/'):
                continue
            if (not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id)
                    or link.path != '/watch' or parse_qs(link.query).get('v') != [video_id]):
                raise ValueError
            return video_id
        return None
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration, RecursionError):
        raise _videos_tab_error() from None


def latest_regular_video(channel_id):
    """At most one public regular video. Never walk the uploads/history feed."""
    if not isinstance(channel_id, str) or not _CHANNEL_ID.fullmatch(channel_id):
        raise ProviderError('Resolve your YouTube channel before checking its Videos tab.')
    video_id = _latest_video_id(_videos_tab_page(channel_id), channel_id)
    if not video_id:
        return None
    data = fetch_video(f'https://www.youtube.com/watch?v={video_id}')
    if data['channel_id'] != channel_id:
        raise _videos_tab_error()
    # An upcoming premiere/live broadcast is not a published video to prepare.
    return None if data['live_status'] in {'live', 'upcoming'} else data


def fetch_video(video_url):
    """Resolve a public video URL; channel_id lets the caller enforce ownership."""
    parsed, parts = _youtube_url(video_url, allow_short=True)
    if parsed.hostname in {'youtu.be', 'www.youtu.be'} and len(parts) == 1:
        video_id = parts[0]
    elif parts == ['watch']:
        ids = parse_qs(parsed.query).get('v', [])
        video_id = ids[0] if len(ids) == 1 else ''
    elif len(parts) == 2 and parts[0] in {'shorts', 'live', 'embed'}:
        video_id = parts[1]
    else:
        video_id = ''
    if not _VIDEO_ID.fullmatch(video_id):
        raise ProviderError('Use a valid YouTube watch, Shorts or youtu.be video link.')
    items = _items(_json_request(API_ROOT + 'videos', params={'part': 'snippet,status', 'id': video_id, 'key': _api_key()}))
    if not items:
        raise ProviderError('This YouTube video could not be found. Check that it is public and the URL is correct.')
    try:
        item = items[0]
        snippet = item['snippet']
        channel_id = snippet['channelId']
        if item['id'] != video_id or not isinstance(channel_id, str) or not _CHANNEL_ID.fullmatch(channel_id):
            raise ValueError
        if item.get('status', {}).get('privacyStatus') in {'private', 'unlisted'}:
            raise ProviderError('Only public YouTube videos can be imported.')
        result = _video_metadata(video_id, snippet, snippet['publishedAt'])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _invalid_response() from None
    return {**result, 'channel_id': channel_id, 'live_status': snippet.get('liveBroadcastContent', 'none')}


def _access_token():
    location = getattr(settings, 'YOUTUBE_BLOG_CREDENTIALS_FILE', '')
    if not location:
        raise ProviderError('Automatic captions need the channel owner\'s OAuth credentials. Set YOUTUBE_BLOG_CREDENTIALS_FILE, or upload a script manually.')
    try:
        with Path(location).open('rb') as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError
        credentials = json.loads(raw)
        if not isinstance(credentials, dict):
            raise ValueError
        fields = {key: credentials[key] for key in ('client_id', 'client_secret', 'refresh_token')}
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise ProviderError('The YouTube credential file must be readable JSON with client_id, client_secret and refresh_token. Upload a script manually until it is configured.') from None
    payload = _json_request(TOKEN_URL, data={**fields, 'grant_type': 'refresh_token'}, oauth=True)
    token = payload.get('access_token')
    if not isinstance(token, str) or not token or re.search(r'[\x00-\x20\x7f]', token):
        raise ProviderError('YouTube did not return a valid access token. Reconnect the channel owner and update the credential file.')
    return token


def fetch_transcript(video_id, language='en'):
    """Download available owner-authorized captions in the requested language.

    We do not scrape public transcripts or request machine translation. Missing,
    draft and failed tracks require a manual script upload.
    """
    if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id):
        raise ProviderError('The YouTube video ID is invalid.')
    if not isinstance(language, str) or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
        raise ProviderError('Use a caption language code such as en or en-US.')
    headers = {'Authorization': 'Bearer ' + _access_token()}
    tracks = _items(_json_request(API_ROOT + 'captions', params={'part': 'snippet', 'videoId': video_id}, headers=headers, captions=True))
    available = []
    for track in tracks:
        snippet = track.get('snippet')
        track_id = track.get('id')
        if not isinstance(snippet, dict) or not isinstance(track_id, str) or not track_id or len(track_id) > 512:
            raise _invalid_response()
        track_language = snippet.get('language', '')
        if not isinstance(track_language, str):
            raise _invalid_response()
        if snippet.get('status') != 'serving' or snippet.get('isDraft'):
            continue
        requested = language.lower()
        actual = track_language.lower()
        # Exact language first; matching regional variants are a fallback, never translations.
        if actual == requested or actual.split('-')[0] == requested.split('-')[0]:
            available.append((actual != requested, snippet.get('trackKind') == 'ASR', track_id))
    if not available:
        raise ProviderError('No ready captions are available in the requested language. Add captions in YouTube Studio or upload the script manually.')
    track_id = sorted(available)[0][2]
    response = None
    try:
        response = requests.get(API_ROOT + 'captions/' + quote(track_id, safe=''),
                                params={'tfmt': 'srt'}, headers=headers, timeout=TIMEOUT,
                                allow_redirects=False, stream=True)
        _status_error(response, captions=True)
        chunks, size, deadline = [], 0, time.monotonic() + 30
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_TRANSCRIPT_BYTES:
                raise ProviderError('These captions exceed the 1 MiB import limit. Upload a shorter script manually.')
            if time.monotonic() > deadline:
                raise ProviderError('The caption download took too long. Please try again later.')
            chunks.append(chunk)
        raw = b''.join(chunks).decode('utf-8-sig')
    except requests.RequestException:
        raise ProviderError('Could not download the YouTube captions. Try again or upload the script manually.') from None
    except UnicodeError:
        raise ProviderError('YouTube returned captions in an unreadable encoding. Upload a UTF-8 script manually.') from None
    finally:
        if response is not None:
            response.close()
    transcript = normalize_transcript(raw)
    if not transcript:
        raise ProviderError('These YouTube captions contain no readable script. Upload the script manually.')
    return transcript


def normalize_transcript(text):
    """Normalize UTF-8 plain text/Markdown or SRT/WebVTT into readable script.

    Markdown structure is retained for authored scripts. Subtitle timestamps,
    identifiers, settings and cue markup are removed; spoken text is preserved.
    """
    if not isinstance(text, str):
        raise ProviderError('Upload or paste a text script using UTF-8 encoding.')
    if len(text.encode('utf-8')) > MAX_TRANSCRIPT_BYTES:
        raise ProviderError('The script exceeds the 1 MiB import limit.')
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    lines = text.splitlines()
    is_subtitle = any(_TIME_LINE.match(line) for line in lines) or text.startswith('WEBVTT')
    if not is_subtitle:
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(line.rstrip() for line in lines)).strip()
    cues = []
    for block in re.split(r'\n\s*\n', text):
        block_lines = block.splitlines()
        timing = next((i for i, line in enumerate(block_lines) if _TIME_LINE.match(line)), None)
        if timing is None:
            continue
        cue = ' '.join(line.strip() for line in block_lines[timing + 1:])
        cue = re.sub(r'<[^>]*>', '', cue)
        cue = html.unescape(cue)
        cue = re.sub(r'\s+', ' ', cue).strip()
        if cue:
            cues.append(cue)
    return '\n'.join(cues)
