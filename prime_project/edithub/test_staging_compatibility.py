"""Keep staging's legacy achievement behavior when introducing the V2 league."""
import json
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from edithub.models import EditorApplication, EditorTitle, EditSubmission, UserTitleUnlock
from edithub.utils import get_youtube_channel_id_from_link, verify_video_belongs_to_channel
from edithub.views import get_available_titles


class LegacyTitleCompatibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='legacy-title@example.test', username='legacy-title', is_verified=True)
        # Restored historical records do not replay save signals.
        self.application = EditorApplication.objects.bulk_create([EditorApplication(
            user=self.user, channel_link='https://youtube.com/@legacy-title',
            channel_type='youtube', status='accepted', channel_verified=True,
        )])[0]
        EditSubmission.objects.bulk_create([EditSubmission(
            user=self.user, approved_application=self.application,
            channel_link=self.application.channel_link, channel_type='youtube',
            video_url='https://youtube.com/shorts/abcdefghijk', status='verified',
            calculated_points=Decimal('125.50'),
        )])
        self.title = EditorTitle.objects.create(
            name='Legacy point achievement', unlock_method='achievement',
            achievement_type='total_points', achievement_threshold=100,
        )

    def title_data(self):
        request = RequestFactory().get('/edithub/titles/')
        request.user = self.user
        response = get_available_titles(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        return next(row for row in payload['titles_by_category']['general'] if row['id'] == self.title.pk)

    def test_historical_points_unlock_achievement_on_first_read(self):
        self.assertFalse(UserTitleUnlock.objects.filter(user=self.user, title=self.title).exists())
        data = self.title_data()
        self.assertTrue(data['is_unlocked'])
        self.assertEqual(data['achievement_progress']['current_value'], 125.5)
        self.assertEqual(data['achievement_progress']['progress_percentage'], 100)
        self.title_data()
        self.assertEqual(UserTitleUnlock.objects.filter(user=self.user, title=self.title).count(), 1)

    def test_already_unlocked_achievement_still_reports_progress(self):
        UserTitleUnlock.objects.create(user=self.user, title=self.title, unlock_method='achievement')
        data = self.title_data()
        self.assertTrue(data['is_unlocked'])
        self.assertEqual(data['achievement_progress']['current_value'], 125.5)
        self.assertEqual(data['achievement_progress']['threshold'], 100)


@override_settings(YOUTUBE_API_KEY='private-test-key')
class LegacyYouTubeIdentityCompatibilityTests(SimpleTestCase):
    channel_id = 'UC' + 'A' * 22

    @patch('edithub.utils.requests.get')
    def test_supported_channel_forms_use_exact_lookup(self, get):
        get.return_value = Mock(status_code=200, json=Mock(return_value={'items': [{'id': self.channel_id}]}))
        for path, selector, value in (
            (f'channel/{self.channel_id}', 'id', self.channel_id),
            ('@2.0Transformers/shorts', 'forHandle', '@2.0Transformers'),
            ('user/Creator', 'forUsername', 'Creator'),
        ):
            with self.subTest(path=path):
                get.reset_mock()
                self.assertEqual(get_youtube_channel_id_from_link('https://www.youtube.com/' + path), self.channel_id)
                get.assert_called_once()
                self.assertEqual(get.call_args.args[0], 'https://www.googleapis.com/youtube/v3/channels')
                self.assertEqual(get.call_args.kwargs['params'][selector], value)

    @patch('edithub.utils.requests.get')
    def test_unsupported_or_deceptive_links_never_use_search(self, get):
        for link in (
            'https://youtube.com.evil.test/@Creator', 'https://evil.test/youtube.com/@Creator',
            'https://user@youtube.com/@Creator', 'https://youtube.com:444/@Creator',
            'https://youtube.com/c/Creator', 'https://youtube.com/channel/UCtoo-short',
            'https://youtu.be/abcdefghijk', 'https://youtube.com/@Creator/arbitrary',
        ):
            with self.subTest(link=link):
                self.assertIsNone(get_youtube_channel_id_from_link(link))
        get.assert_not_called()

    @patch('edithub.utils.requests.get')
    def test_missing_or_wrong_channel_does_not_fall_back(self, get):
        for items in ([], [{'id': 'UC' + 'B' * 22}], [{'id': 'invalid'}]):
            with self.subTest(items=items):
                get.reset_mock()
                get.return_value = Mock(status_code=200, json=Mock(return_value={'items': items}))
                self.assertIsNone(get_youtube_channel_id_from_link(f'https://youtube.com/channel/{self.channel_id}'))
                get.assert_called_once()

    @patch('edithub.utils.requests.get', side_effect=requests.Timeout('private-test-key'))
    def test_provider_error_is_safe_and_has_no_search_fallback(self, get):
        with self.assertLogs('edithub.utils', level='WARNING') as logs:
            self.assertIsNone(get_youtube_channel_id_from_link('https://youtube.com/@Creator'))
        self.assertNotIn('private-test-key', str(logs.output))
        get.assert_called_once()

    @patch('edithub.utils.requests.get')
    def test_video_cannot_pass_via_custom_url_after_channel_resolution_fails(self, get):
        get.return_value = Mock(status_code=200, json=Mock(return_value={'items': [{
            'snippet': {'channelId': self.channel_id, 'customUrl': '@Creator-other'},
        }]}))
        valid, _ = verify_video_belongs_to_channel(
            'https://youtube.com/shorts/abcdefghijk', 'https://youtube.com/c/Creator', 'youtube')
        self.assertFalse(valid)
        get.assert_called_once()
