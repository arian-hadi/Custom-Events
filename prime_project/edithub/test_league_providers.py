"""Mock-only contract tests: no provider credentials, network or database needed."""
from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

import requests
from django.test import override_settings

from edithub.league.providers import (
    ENDPOINTS, ProviderError, TikTokCredential, canonical_video, fetch_video,
    list_channel_video_ids, require_channel, resolve_youtube_channel,
)

VIDEO = 'AbCdEfGhI_1'
CHANNEL = 'UC' + 'A' * 22
OTHER_CHANNEL = 'UC' + 'B' * 22
TIKTOK_ID = '7080217258545735586'
TIKTOK_OPEN_ID = 'verified-editor-open-id'


def response(payload, status=200):
    return Mock(status_code=status, json=Mock(return_value=payload))


def youtube_video():
    return {'items': [{
        'id': VIDEO,
        'snippet': {'channelId': CHANNEL, 'title': 'An older edit', 'publishedAt': '2025-01-01T12:00:00Z', 'liveBroadcastContent': 'none'},
        'statistics': {'likeCount': '8200', 'viewCount': '100000'},
        'status': {'privacyStatus': 'public', 'uploadStatus': 'processed'},
        'contentDetails': {'duration': 'PT30S'},
    }]}


def tiktok_video():
    return {'error': {'code': 'ok'}, 'data': {'videos': [{
        'id': TIKTOK_ID, 'title': 'An older edit', 'create_time': 1735732800,
        'share_url': f'https://www.tiktok.com/@editor/video/{TIKTOK_ID}?tracking=ignored',
        'like_count': 8200, 'view_count': 100000,
    }]}}


class CanonicalVideoTests(TestCase):
    def test_youtube_variants_share_one_identity(self):
        for url in (
            f'https://www.youtube.com/watch?v={VIDEO}&t=42',
            f'https://youtu.be/{VIDEO}?si=tracking',
            f'http://m.youtube.com/shorts/{VIDEO}',
            f'https://youtube.com/embed/{VIDEO}',
            f'https://www.youtube-nocookie.com/embed/{VIDEO}',
            f'https://youtube.com/live/{VIDEO}',
        ):
            with self.subTest(url=url):
                self.assertEqual(canonical_video(url), ('youtube', VIDEO, f'https://www.youtube.com/watch?v={VIDEO}'))

    def test_tiktok_variants_keep_id_without_tracking(self):
        self.assertEqual(canonical_video(f'https://m.tiktok.com/@editor/video/{TIKTOK_ID}/?lang=en'),
                         ('tiktok', TIKTOK_ID, f'https://www.tiktok.com/@editor/video/{TIKTOK_ID}'))

    @patch('edithub.league.providers.requests.get')
    def test_rejects_spoofed_hosts_shortlinks_and_ambiguous_urls_without_fetching(self, get):
        for url in (
            f'https://youtube.com.evil.test/watch?v={VIDEO}',
            f'https://youtube.com@evil.test/watch?v={VIDEO}',
            f'https://user:password@youtube.com/watch?v={VIDEO}',
            f'https://youtube.com:8443/watch?v={VIDEO}',
            f'https://youtube.com/watch?v={VIDEO}&v={VIDEO}',
            f'https://youtube.com/watch?v={VIDEO}/extra',
            f'https://youtube.com/shorts/{VIDEO}/extra',
            f'https://youtu.be/{VIDEO}%2Fextra',
            'http://127.0.0.1/private', 'file:///etc/passwd',
            'https://vm.tiktok.com/opaque/', 'https://www.tiktok.com/t/opaque/',
            'https://www.youtube.com/@channel', 'https://www.tiktok.com/@editor',
            'https://www.youtube.com\\@evil.test/watch?v=' + VIDEO,
        ):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                canonical_video(url)
        get.assert_not_called()


class YouTubeProviderTests(TestCase):
    @patch('edithub.league.providers.requests.get')
    def test_league_key_is_preferred_and_legacy_key_remains_a_fallback(self, get):
        get.return_value = response(youtube_video())
        for league_key, legacy_key, expected in (
            ('league-only', '', 'league-only'),
            ('league-key', 'legacy-key', 'league-key'),
            ('', 'legacy-key', 'legacy-key'),
        ):
            with self.subTest(league_key=league_key), override_settings(
                LEAGUE_YOUTUBE_API_KEY=league_key, YOUTUBE_API_KEY=legacy_key,
            ):
                fetch_video('youtube', VIDEO)
                self.assertEqual(get.call_args.kwargs['params']['key'], expected)
        with override_settings(LEAGUE_YOUTUBE_API_KEY='league-key', YOUTUBE_API_KEY='legacy-key'):
            fetch_video('youtube', VIDEO, credential='explicit-key')
            self.assertEqual(get.call_args.kwargs['params']['key'], 'explicit-key')

    @patch('edithub.league.providers.requests.get')
    def test_lifetime_metrics_and_real_completion_are_preserved(self, get):
        get.return_value = response(youtube_video())
        started = datetime(2026, 9, 25, 23, 59, 59, tzinfo=timezone.utc)
        completed = datetime(2026, 9, 26, 0, 0, 1, tzinfo=timezone.utc)
        with patch('edithub.league.providers.utc_now', side_effect=[started, started, completed]):
            observed = fetch_video('youtube', VIDEO, credential='private-test-key')
        self.assertEqual(observed['likes'], 8200)  # Not 200 relative to earlier observations.
        self.assertEqual(observed['views'], 100000)
        self.assertEqual(observed['completed_at'], completed)  # Never backdated before cutoff.
        self.assertEqual(observed['observed_at'], completed)
        self.assertEqual(observed['video_format'], 'unknown')  # PT30S is not proof of Shorts.
        self.assertEqual(observed['published_at'].year, 2025)
        self.assertEqual(observed['channel_id'], CHANNEL)
        self.assertNotIn('private-test-key', str(observed))
        self.assertEqual(get.call_args.args[0], ENDPOINTS['youtube_videos'])
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(get.call_args.kwargs['timeout'], (3.05, 10))

    @patch('edithub.league.providers.requests.get')
    def test_zero_is_valid_but_absent_or_malformed_counters_are_not(self, get):
        for invalid in (None, -1, '-1', '1.2', 1.2, True, 'NaN', '', 2**63):
            payload = youtube_video()
            payload['items'][0]['statistics']['likeCount'] = invalid
            get.return_value = response(payload)
            with self.subTest(value=invalid), self.assertRaises(ProviderError):
                fetch_video('youtube', VIDEO, 'test-key')
        payload = youtube_video()
        payload['items'][0]['statistics'] = {'likeCount': '0', 'viewCount': '0'}
        get.return_value = response(payload)
        self.assertEqual(fetch_video('youtube', VIDEO, 'test-key')['likes'], 0)

    @patch('edithub.league.providers.requests.get')
    def test_deleted_private_live_wrong_identity_or_missing_date_fails_closed(self, get):
        cases = [{'items': []}]
        for section, key, value in (
            ('status', 'privacyStatus', 'private'), ('status', 'privacyStatus', 'unlisted'),
            ('status', 'uploadStatus', 'uploaded'), ('snippet', 'liveBroadcastContent', 'live'),
            ('snippet', 'publishedAt', None), ('snippet', 'publishedAt', '2099-01-01T00:00:00Z'),
            ('snippet', 'publishedAt', '2025-01-01T00:00:00'), ('snippet', 'channelId', None),
        ):
            payload = youtube_video()
            payload['items'][0][section][key] = value
            cases.append(payload)
        wrong_id = youtube_video()
        wrong_id['items'][0]['id'] = 'WrongVideo1'
        cases.append(wrong_id)
        for payload in cases:
            get.return_value = response(payload)
            with self.subTest(payload=payload), self.assertRaises(ProviderError):
                fetch_video('youtube', VIDEO, 'test-key')

    @patch('edithub.league.providers.requests.get')
    def test_counter_decrease_is_not_replaced_by_a_maximum(self, get):
        first, corrected = youtube_video(), youtube_video()
        corrected['items'][0]['statistics']['likeCount'] = '8000'
        get.side_effect = [response(first), response(corrected)]
        self.assertEqual(fetch_video('youtube', VIDEO, 'test-key')['likes'], 8200)
        self.assertEqual(fetch_video('youtube', VIDEO, 'test-key')['likes'], 8000)

    @patch('edithub.league.providers.requests.get')
    def test_request_errors_do_not_expose_api_key(self, get):
        get.side_effect = requests.Timeout('https://provider.test/?key=secret-key')
        with self.assertRaises(ProviderError) as caught:
            fetch_video('youtube', VIDEO, 'secret-key')
        self.assertNotIn('secret-key', str(caught.exception))
        self.assertTrue(caught.exception.retryable)
        self.assertIsNotNone(caught.exception.requested_at)
        self.assertIsNotNone(caught.exception.completed_at)

    @patch('edithub.league.providers.requests.get')
    def test_redirect_and_quota_failures_are_not_followed(self, get):
        for status in (302, 403, 429, 500):
            get.return_value = response({}, status)
            with self.subTest(status=status), self.assertRaises(ProviderError) as caught:
                fetch_video('youtube', VIDEO, 'test-key')
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertEqual(caught.exception.retryable, status in (429, 500))

    @patch('edithub.league.providers.requests.get')
    def test_missing_key_makes_no_request(self, get):
        with self.assertRaises(ProviderError):
            fetch_video('youtube', VIDEO, '')
        get.assert_not_called()

    @patch('edithub.league.providers.requests.get')
    def test_channel_id_handle_and_legacy_username_use_exact_endpoints(self, get):
        get.return_value = response({'items': [{'id': CHANNEL}]})
        for path, expected in (
            (f'channel/{CHANNEL}', {'id': CHANNEL}), ('@Editor/videos', {'forHandle': '@Editor'}),
            ('user/Creator', {'forUsername': 'Creator'}),
        ):
            with self.subTest(path=path):
                self.assertEqual(resolve_youtube_channel('https://youtube.com/' + path, 'test-key'), CHANNEL)
                for name, value in expected.items():
                    self.assertEqual(get.call_args.kwargs['params'][name], value)
                self.assertEqual(get.call_args.args[0], ENDPOINTS['youtube_channels'])

    @patch('edithub.league.providers.requests.get')
    def test_custom_channel_or_display_name_never_falls_back_to_search(self, get):
        for url in ('https://youtube.com/c/Editor', 'https://evil.test/@Editor', 'https://youtube.com/Editor'):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                resolve_youtube_channel(url, 'test-key')
        get.assert_not_called()

    @patch('edithub.league.providers.requests.get')
    def test_wrong_channel_cannot_pass_identity_verification(self, get):
        get.return_value = response({'items': [{'id': OTHER_CHANNEL}]})
        with self.assertRaises(ProviderError):
            resolve_youtube_channel(f'https://youtube.com/channel/{CHANNEL}', 'test-key')
        with self.assertRaises(ProviderError):
            require_channel({'channel_id': OTHER_CHANNEL}, CHANNEL)


class TikTokProviderTests(TestCase):
    def setUp(self):
        self.credential = TikTokCredential('secret-editor-token', TIKTOK_OPEN_ID)

    @patch('edithub.league.providers.requests.post')
    @patch('edithub.league.providers.requests.get')
    def test_token_subject_is_checked_before_video_query(self, get, post):
        get.return_value = response({'error': {'code': 'ok'}, 'data': {'user': {'open_id': TIKTOK_OPEN_ID}}})
        post.return_value = response(tiktok_video())
        observed = fetch_video('tiktok', TIKTOK_ID, self.credential)
        self.assertEqual(observed['channel_id'], TIKTOK_OPEN_ID)
        self.assertEqual(observed['likes'], 8200)
        self.assertEqual(observed['video_format'], 'video')
        self.assertNotIn(self.credential.access_token, repr(self.credential))
        self.assertNotIn(self.credential.access_token, str(observed))
        self.assertEqual(get.call_args.args[0], ENDPOINTS['tiktok_user'])
        self.assertEqual(post.call_args.args[0], ENDPOINTS['tiktok_query'])
        self.assertEqual(post.call_args.kwargs['json'], {'filters': {'video_ids': [TIKTOK_ID]}})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    @patch('edithub.league.providers.requests.post')
    @patch('edithub.league.providers.requests.get')
    def test_another_creators_token_cannot_query(self, get, post):
        get.return_value = response({'error': {'code': 'ok'}, 'data': {'user': {'open_id': 'another-person'}}})
        with self.assertRaises(ProviderError) as caught:
            fetch_video('tiktok', TIKTOK_ID, self.credential)
        self.assertEqual(caught.exception.code, 'identity_mismatch')
        post.assert_not_called()

    @patch('edithub.league.providers.requests.post')
    @patch('edithub.league.providers.requests.get')
    def test_no_global_token_or_browser_dictionary_fallback(self, get, post):
        for credential in (None, 'global-token', {'access_token': 'browser-input', 'expected_open_id': TIKTOK_OPEN_ID}):
            with self.subTest(credential=credential), self.assertRaises(ProviderError):
                fetch_video('tiktok', TIKTOK_ID, credential)
        get.assert_not_called()
        post.assert_not_called()

    @patch('edithub.league.providers.requests.post')
    @patch('edithub.league.providers.requests.get')
    def test_private_other_creator_missing_counter_and_error_payload_rejected(self, get, post):
        get.return_value = response({'error': {'code': 'ok'}, 'data': {'user': {'open_id': TIKTOK_OPEN_ID}}})
        missing = tiktok_video()
        del missing['data']['videos'][0]['like_count']
        wrong_link = tiktok_video()
        wrong_link['data']['videos'][0]['share_url'] = 'https://evil.test/video/' + TIKTOK_ID
        wrong_id = tiktok_video()
        wrong_id['data']['videos'][0]['id'] = '1234567890123456789'
        for payload in (
            {'error': {'code': 'ok'}, 'data': {'videos': []}},
            {'error': {'code': 'access_token_invalid', 'message': 'secret-editor-token'}, 'data': {}},
            missing, wrong_link, wrong_id,
        ):
            post.return_value = response(payload)
            with self.subTest(payload=payload), self.assertRaises(ProviderError) as caught:
                fetch_video('tiktok', TIKTOK_ID, self.credential)
            self.assertNotIn('secret-editor-token', str(caught.exception))


class ComparisonDiscoveryTests(TestCase):
    @patch('edithub.league.providers.requests.get')
    def test_youtube_uses_uploads_playlist_not_search_or_fabricated_history(self, get):
        get.side_effect = [
            response({'items': [{'id': CHANNEL, 'contentDetails': {'relatedPlaylists': {'uploads': 'UU' + 'A' * 22}}}]}),
            response({'items': [{'contentDetails': {'videoId': VIDEO}}], 'nextPageToken': 'next-page'}),
        ]
        batch = list_channel_video_ids('youtube', CHANNEL, 'test-key', limit=8)
        self.assertEqual(batch, {'video_ids': [VIDEO], 'cursor': 'next-page', 'has_more': True})
        self.assertEqual(get.call_args.args[0], ENDPOINTS['youtube_playlist'])
        self.assertNotIn('likes', batch)

    @patch('edithub.league.providers.requests.post')
    @patch('edithub.league.providers.requests.get')
    def test_tiktok_discovery_requires_the_same_authorized_creator(self, get, post):
        credential = TikTokCredential('secret', TIKTOK_OPEN_ID)
        get.return_value = response({'error': {'code': 'ok'}, 'data': {'user': {'open_id': TIKTOK_OPEN_ID}}})
        post.return_value = response({'error': {'code': 'ok'}, 'data': {'videos': [{'id': TIKTOK_ID}], 'has_more': False}})
        self.assertEqual(list_channel_video_ids('tiktok', TIKTOK_OPEN_ID, credential)['video_ids'], [TIKTOK_ID])
        with self.assertRaises(ProviderError):
            list_channel_video_ids('tiktok', 'another-person', credential)

    @patch('edithub.league.providers.requests.get')
    def test_duplicate_comparison_ids_rejected(self, get):
        get.side_effect = [
            response({'items': [{'id': CHANNEL, 'contentDetails': {'relatedPlaylists': {'uploads': 'UU' + 'A' * 22}}}]}),
            response({'items': [{'contentDetails': {'videoId': VIDEO}}, {'contentDetails': {'videoId': VIDEO}}]}),
        ]
        with self.assertRaises(ProviderError):
            list_channel_video_ids('youtube', CHANNEL, 'test-key')
