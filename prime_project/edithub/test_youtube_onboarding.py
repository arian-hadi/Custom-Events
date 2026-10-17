from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from edithub.utils import fetch_youtube_channel_data


@override_settings(YOUTUBE_API_KEY='private-test-key')
class YouTubeHandleLookupTests(SimpleTestCase):
    @patch('edithub.utils.requests.get')
    def test_exact_dotted_handle_uses_channels_not_search(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'items': [{
            'snippet': {'title': '2.0Transformers', 'thumbnails': {'high': {'url': 'https://example.test/image.png'}}},
            'statistics': {'subscriberCount': '123'},
        }]}
        result = fetch_youtube_channel_data('https://www.youtube.com/@2.0Transformers')
        self.assertEqual(result['channel_name'], '2.0Transformers')
        self.assertEqual(result['subscriber_count'], 123)
        self.assertIsNone(result['error'])
        get.assert_called_once_with('https://www.googleapis.com/youtube/v3/channels',
            params={'part': 'snippet,statistics', 'forHandle': '@2.0Transformers', 'key': 'private-test-key'}, timeout=10)

    @patch('edithub.utils.requests.get')
    def test_not_found_and_provider_failures_are_distinct(self, get):
        for status, data, code in [
            (200, {'items': []}, 'channel_not_found'),
            (403, {'error': {'errors': [{'reason': 'quotaExceeded'}]}}, 'quota_exceeded'),
            (400, {'error': {'message': 'private-test-key'}}, 'configuration_error'),
            (503, {}, 'provider_unavailable'),
        ]:
            with self.subTest(status=status):
                get.return_value = Mock(status_code=status)
                get.return_value.json.return_value = data
                result = fetch_youtube_channel_data('https://www.youtube.com/@creator')
                self.assertEqual(result['error_code'], code)
                self.assertNotIn('private-test-key', str(result))

    @patch('edithub.utils.requests.get', side_effect=requests.Timeout('private-test-key'))
    def test_transport_error_does_not_log_key(self, get):
        with self.assertLogs('edithub.utils', level='WARNING') as logs:
            result = fetch_youtube_channel_data('https://www.youtube.com/@creator')
        self.assertEqual(result['error_code'], 'provider_unavailable')
        self.assertNotIn('private-test-key', str(logs.output) + str(result))

    @override_settings(YOUTUBE_API_KEY='')
    @patch('edithub.utils.requests.get')
    def test_missing_key_is_configuration_error_without_network(self, get):
        result = fetch_youtube_channel_data('https://www.youtube.com/@creator')
        self.assertEqual(result['error_code'], 'configuration_error')
        get.assert_not_called()
