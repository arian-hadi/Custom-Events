"""History harvesting integration, isolated database and mocked provider I/O."""
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from edithub.league import services
from edithub.league_models import CompetitionEntry, CompetitionWeek, LeagueHistorySync, MetricSnapshot, ScoringVersion
from edithub.models import EditorApplication
from edithub.test_league_core import fixture_config


NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
START = datetime(2026, 9, 28, tzinfo=timezone.utc)
VIDEO = 'AbCdEfGhI_1'
OTHER = 'AbCdEfGhI_2'
CHANNEL = 'UC' + 'A' * 22


@override_settings(LEAGUE_ENABLED=True)
class LeagueHistoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='history@example.test', username='history', is_verified=True)
        self.app = EditorApplication(user=self.user, channel_link=f'https://youtube.com/channel/{CHANNEL}',
            channel_type='youtube', status='accepted', channel_verified=True, editing_area='transformers')
        EditorApplication.objects.bulk_create([self.app])
        self.version = ScoringVersion.objects.create(name='history-fixture', config=fixture_config(), rules_confirmed=True,
            calibrated=True, calibration_notes='Synthetic isolated fixture; not real calibration.')
        self.week = services.ensure_week(START, self.version)
        self.entry = CompetitionEntry.objects.create(week=self.week, editor=self.user, approved_application=self.app,
            platform='youtube', video_id=VIDEO, channel_id=CHANNEL, video_format='short', published_at=START-timedelta(days=100),
            canonical_url=f'https://youtube.com/watch?v={VIDEO}', state='queued')
        for name, kwargs in (
            ('timezone.now', {'return_value': NOW}),
            ('approved_channel_context', {'return_value': ('youtube', None, CHANNEL, {})}),
            ('list_channel_video_ids', {'return_value': {'video_ids': [VIDEO, OTHER], 'cursor': None, 'has_more': False}}),
            ('fetch_verified_video_id', {'side_effect': self.observation}),
        ):
            mocked = patch('edithub.management.commands.league_history.' + name, **kwargs)
            setattr(self, name.split('.')[-1], mocked.start())
            self.addCleanup(mocked.stop)

    def observation(self, application, video_id, **kwargs):
        return {'platform': 'youtube', 'video_id': video_id, 'channel_id': CHANNEL, 'video_format': 'short',
            'published_at': START-timedelta(days=110), 'requested_at': self.now.return_value,
            'completed_at': self.now.return_value, 'likes': 500, 'views': 8000, 'provider': 'isolated-test', 'status': 'success'}

    def collect(self, **options):
        output = StringIO()
        call_command('league_history', stdout=output, **options)
        return output.getvalue()

    def test_collects_real_observed_lifetime_history_and_never_scores(self):
        self.collect()
        snapshot = MetricSnapshot.objects.get()
        self.assertIsNone(snapshot.entry_id)
        self.assertEqual(snapshot.video_id, OTHER)
        self.assertEqual(snapshot.likes, 500)
        self.assertEqual(snapshot.completed_at, NOW)
        self.assertEqual(snapshot.received_at, NOW)
        self.assertEqual(snapshot.provenance['application_id'], self.app.pk)
        self.assertEqual(LeagueHistorySync.objects.get().status, 'success')
        self.assertFalse(self.week.results.exists())
        self.fetch_verified_video_id.assert_called_once()

    def test_success_and_failure_attempts_are_paced_hourly(self):
        self.list_channel_video_ids.side_effect = ValueError('secret-token-must-not-be-saved')
        self.collect()
        self.now.return_value += timedelta(minutes=1)
        self.collect()
        self.assertEqual(self.list_channel_video_ids.call_count, 1)
        sync = LeagueHistorySync.objects.get()
        self.assertEqual(sync.error_code, 'ValueError')
        self.assertEqual(sync.status, 'unavailable')
        self.assertEqual(sync.failures, 1)
        self.assertFalse(MetricSnapshot.objects.exists())
        self.now.return_value = NOW+timedelta(hours=1)
        self.list_channel_video_ids.side_effect = None
        self.collect()
        self.assertEqual(self.list_channel_video_ids.call_count, 2)
        sync.refresh_from_db()
        self.assertEqual(sync.status, 'success')

    def test_limits_video_requests_and_skips_another_app(self):
        self.list_channel_video_ids.return_value['video_ids'] = [VIDEO, OTHER, 'AbCdEfGhI_3', 'AbCdEfGhI_4']
        self.collect(limit=2, application=self.app.pk+1)
        self.list_channel_video_ids.assert_not_called()
        self.collect(limit=2)
        self.assertEqual(self.fetch_verified_video_id.call_count, 2)
        self.assertEqual(MetricSnapshot.objects.count(), 2)

    def test_disabled_revoked_or_finished_only_channels_do_not_call_provider(self):
        with override_settings(LEAGUE_ENABLED=False):
            self.collect()
        EditorApplication.objects.filter(pk=self.app.pk).update(removal_requested=True)
        self.collect()
        EditorApplication.objects.filter(pk=self.app.pk).update(removal_requested=False)
        CompetitionWeek.objects.filter(pk=self.week.pk).update(state='finalized')
        self.collect()
        self.approved_channel_context.assert_not_called()

    def test_missing_classification_and_missing_metrics_never_become_fake_history(self):
        for invalid in ({'video_format': 'unknown'}, {'likes': None}):
            data = self.observation(self.app, OTHER)
            data.update(invalid)
            self.fetch_verified_video_id.side_effect = None
            self.fetch_verified_video_id.return_value = data
            self.collect()
            self.now.return_value += timedelta(hours=1)
        self.assertEqual(self.fetch_verified_video_id.call_count, 2)
        self.assertFalse(MetricSnapshot.objects.exists())
        self.assertEqual(LeagueHistorySync.objects.get().failures, 1)

    def test_current_baseline_is_immutable_when_history_arrives_later(self):
        self.now.return_value = START
        week = services.activate_week(self.week, now=START)
        baseline = self.entry.baseline
        self.assertEqual(baseline.sample_count, 0)
        self.now.return_value = START+timedelta(days=1)
        self.collect()
        baseline.refresh_from_db()
        self.assertEqual(baseline.sample_count, 0)
        self.assertEqual(baseline.sample_ids, [])
        self.assertEqual(MetricSnapshot.objects.count(), 1)
        self.assertEqual(MetricSnapshot.objects.get().received_at, self.now.return_value)

    def test_closing_metrics_take_priority_over_history(self):
        CompetitionWeek.objects.filter(pk=self.week.pk).update(state='live', activated_at=START)
        self.now.return_value = self.week.cutoff_at-timedelta(minutes=29)
        self.collect()
        self.approved_channel_context.assert_not_called()
        self.assertFalse(LeagueHistorySync.objects.exists())

    def test_expired_cycle_budget_starts_no_requests(self):
        with patch('edithub.management.commands.league_history.time.monotonic', side_effect=[0, 31]):
            self.collect()
        self.approved_channel_context.assert_not_called()

    def test_previous_eligible_competition_video_can_supply_history_for_another_edit(self):
        older = services.ensure_week(START-timedelta(days=7), self.version)
        CompetitionWeek.objects.filter(pk=older.pk).update(state='finalized')
        CompetitionEntry.objects.create(week=older, editor=self.user, approved_application=self.app,
            platform='youtube', video_id=OTHER, channel_id=CHANNEL, video_format='short', published_at=START-timedelta(days=110),
            canonical_url=f'https://youtube.com/watch?v={OTHER}', state='active')
        self.collect()
        self.assertEqual(MetricSnapshot.objects.get().video_id, OTHER)

    def test_discovery_resumes_remaining_candidates_and_then_next_page(self):
        third, fourth = 'AbCdEfGhI_3', 'AbCdEfGhI_4'
        self.list_channel_video_ids.return_value = {'video_ids': [VIDEO, OTHER, third], 'cursor': 'page-2', 'has_more': True}
        self.collect(limit=1)
        sync = LeagueHistorySync.objects.get()
        self.assertEqual(sync.pending_video_ids, [third])
        self.assertEqual(sync.next_cursor, 'page-2')
        self.now.return_value += timedelta(hours=1)
        self.collect(limit=1)
        self.assertEqual(self.list_channel_video_ids.call_count, 1)
        self.assertEqual(MetricSnapshot.objects.count(), 2)
        self.now.return_value += timedelta(hours=1)
        self.list_channel_video_ids.return_value = {'video_ids': [fourth], 'cursor': None, 'has_more': False}
        self.collect(limit=1)
        self.assertEqual(self.list_channel_video_ids.call_args.kwargs['cursor'], 'page-2')
        sync.refresh_from_db()
        self.assertEqual(sync.pending_video_ids, [])
        self.assertIsNone(sync.next_cursor)

    def test_failed_candidate_does_not_starve_later_observations(self):
        third = 'AbCdEfGhI_3'
        self.list_channel_video_ids.return_value['video_ids'] = [OTHER, third]
        self.fetch_verified_video_id.side_effect = [ValueError('unavailable'), self.observation(self.app, third)]
        self.collect()
        self.assertEqual(MetricSnapshot.objects.get().video_id, third)
        sync = LeagueHistorySync.objects.get()
        self.assertEqual((sync.observations, sync.failures, sync.status), (1, 1, 'partial'))
        self.assertEqual(sync.pending_video_ids, [])

    def test_budget_preserves_candidates_not_started(self):
        with patch('edithub.management.commands.league_history.time.monotonic', side_effect=[0, 0, 31]):
            self.collect()
        self.fetch_verified_video_id.assert_not_called()
        sync = LeagueHistorySync.objects.get()
        self.assertEqual(sync.pending_video_ids, [OTHER])
        self.assertEqual(sync.error_code, 'cycle_budget_reached')

    def test_explicit_unknown_format_scope_can_collect_history(self):
        config = self.version.config
        config['supported_formats'] = ['youtube:unknown']
        config['references'] = {key.replace('youtube:short:', 'youtube:unknown:'): value
            for key, value in config['references'].items() if key.startswith('youtube:short:')}
        self.version.config = config
        self.version.save()
        observation = self.observation(self.app, OTHER)
        observation['video_format'] = 'unknown'
        self.fetch_verified_video_id.side_effect = None
        self.fetch_verified_video_id.return_value = observation
        self.collect()
        self.assertEqual(MetricSnapshot.objects.get().video_format, 'unknown')
