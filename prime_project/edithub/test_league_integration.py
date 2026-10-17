"""Approved-channel/provider wiring, without credentials, network or database."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from edithub.league.integration import ProviderSetupRequired, fetch_verified_video
from edithub.league.providers import ProviderError


VIDEO = 'AbCdEfGhI_1'
TIKTOK_VIDEO = '7080217258545735586'
CHANNEL = 'UC' + 'A' * 22


class ApprovedChannelIntegrationTests(SimpleTestCase):
    def setUp(self):
        self.application = SimpleNamespace(pk=7, user_id=11, status='accepted', channel_verified=True,
            removal_requested=False, channel_type='youtube', channel_link=f'https://youtube.com/channel/{CHANNEL}')
        for name in ('channel_credentials',):
            mocked = patch('edithub.league.integration.'+name, return_value={})
            setattr(self, name, mocked.start())
            self.addCleanup(mocked.stop)
        provider = patch('edithub.league.providers.fetch_video', return_value={
            'channel_id': CHANNEL, 'video_format': 'unknown', 'canonical_url': f'https://www.youtube.com/watch?v={VIDEO}',
        })
        self.provider = provider.start()
        self.addCleanup(provider.stop)
        resolver = patch('edithub.league.providers.resolve_youtube_channel', return_value=CHANNEL)
        self.resolver = resolver.start()
        self.addCleanup(resolver.stop)

    def test_unapproved_channel_and_platform_mismatch_never_fetch(self):
        for attribute, value in (('status', 'pending'), ('channel_verified', False), ('removal_requested', True)):
            original = getattr(self.application, attribute)
            setattr(self.application, attribute, value)
            with self.assertRaises(ProviderSetupRequired):
                fetch_verified_video(self.application, f'https://youtu.be/{VIDEO}')
            setattr(self.application, attribute, original)
        with self.assertRaises(ProviderSetupRequired):
            fetch_verified_video(self.application, f'https://tiktok.com/@creator/video/{TIKTOK_VIDEO}')
        self.provider.assert_not_called()

    def test_only_trusted_review_can_classify_and_link_crossposted_work(self):
        self.channel_credentials.return_value = {'reviewed_formats': {VIDEO: 'short'},
            'reviewed_content_keys': {VIDEO: 'shared-original-1'}}
        result = fetch_verified_video(self.application, f'https://youtu.be/{VIDEO}')
        self.assertEqual(result['video_format'], 'short')
        self.assertEqual(result['content_key'], 'reviewed:shared-original-1')
        self.assertEqual(result['video_id'], VIDEO)
        self.resolver.assert_called_once_with(self.application.channel_link)

    def test_different_channel_video_fails_owned_identity_check(self):
        self.provider.return_value['channel_id'] = 'UC' + 'B' * 22
        with self.assertRaises(ProviderError):
            fetch_verified_video(self.application, f'https://youtu.be/{VIDEO}')

    def test_tiktok_authorized_share_url_wins_over_untrusted_pasted_handle(self):
        self.application.channel_type = 'tiktok'
        self.channel_credentials.return_value = {'access_token': 'test-token', 'open_id': 'owned-id'}
        self.provider.return_value = {'channel_id': 'owned-id', 'video_format': 'video',
            'canonical_url': f'https://www.tiktok.com/@actual_creator/video/{TIKTOK_VIDEO}'}
        result = fetch_verified_video(self.application, f'https://www.tiktok.com/@fake_handle/video/{TIKTOK_VIDEO}')
        self.assertEqual(result['canonical_url'], self.provider.return_value['canonical_url'])
        self.assertIn('@actual_creator/', result['canonical_url'])
        self.assertEqual(self.provider.call_args.kwargs['credential'].expected_open_id, 'owned-id')
        self.resolver.assert_not_called()

    def test_tiktok_requires_per_editor_authorization_and_checks_returned_owner(self):
        self.application.channel_type = 'tiktok'
        with self.assertRaises(ProviderSetupRequired):
            fetch_verified_video(self.application, f'https://tiktok.com/@creator/video/{TIKTOK_VIDEO}')
        self.provider.assert_not_called()
        self.channel_credentials.return_value = {'access_token': 'test-token', 'open_id': 'owned-id'}
        self.provider.return_value['channel_id'] = 'different-id'
        with self.assertRaises(ProviderError):
            fetch_verified_video(self.application, f'https://tiktok.com/@creator/video/{TIKTOK_VIDEO}')

    def test_malformed_review_mapping_never_creates_arbitrary_identity(self):
        for invalid in ('', {}, 'x'*241):
            self.channel_credentials.return_value = {'reviewed_content_keys': {VIDEO: invalid}}
            with self.assertRaises(ProviderSetupRequired):
                fetch_verified_video(self.application, f'https://youtu.be/{VIDEO}')
