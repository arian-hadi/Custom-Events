from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from edithub.league import services
from edithub.league_models import CompetitionEntry, CompetitionWeek, LeagueSeason, ScoringVersion
from edithub.models import EditorApplication
from platform_api.test_league_api import calibrated_test_config


START = datetime(2026, 9, 28, tzinfo=timezone.utc)
NOW = START+timedelta(days=4, hours=12)


@override_settings(LEAGUE_ENABLED=True)
class LeagueCollectionTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(email='polling@example.test', username='polling', is_verified=True)
        app = EditorApplication(user=user, channel_link='https://youtube.com/@polling', channel_type='youtube',
            status='accepted', channel_verified=True, editing_area='transformers')
        EditorApplication.objects.bulk_create([app])
        season = LeagueSeason.objects.create(year=2026)
        version = ScoringVersion.objects.create(name='collection-fixture', config=calibrated_test_config(),
            rules_confirmed=True, calibrated=True, calibration_notes='Synthetic test fixtures only.')
        self.week = CompetitionWeek.objects.create(season=season, scoring_version=version,
            start_at=START, cutoff_at=START+timedelta(days=5), scoring_date=(START+timedelta(days=4)).date(),
            state='live', activated_at=START)
        self.entry = CompetitionEntry.objects.create(week=self.week, editor=user, approved_application=app, platform='youtube',
            video_id='AbCdEfGhI_1', channel_id='UC'+'A'*22, video_format='short', canonical_url='https://youtube.com/watch?v=AbCdEfGhI_1',
            state='active', published_at=START-timedelta(days=100))
        clock = patch('edithub.management.commands.league_collect.timezone.now', return_value=NOW)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        provider = patch('edithub.management.commands.league_collect.fetch_verified_video', side_effect=self.observation)
        self.provider = provider.start()
        self.addCleanup(provider.stop)

    def observation(self, *_):
        return dict(platform='youtube', video_id=self.entry.video_id, channel_id=self.entry.channel_id,
            video_format='short', published_at=self.entry.published_at, provider='test_provider',
            requested_at=self.clock.return_value, completed_at=self.clock.return_value,
            likes=8200, views=100000, status='success', provenance={'counter_scope': 'lifetime'})

    def collect(self, **options):
        call_command('league_collect', stdout=StringIO(), stderr=StringIO(), **options)

    def test_hourly_polling_instead_of_every_worker_tick(self):
        self.collect()
        self.clock.return_value = NOW+timedelta(minutes=1)
        self.collect()
        self.assertEqual(self.provider.call_count, 1)
        self.clock.return_value = NOW+timedelta(hours=1)
        self.collect()
        self.assertEqual(self.provider.call_count, 2)
        self.assertEqual(self.entry.snapshots.count(), 2)

    def test_last_fifteen_minutes_poll_every_five_minutes(self):
        self.clock.return_value = self.week.cutoff_at-timedelta(minutes=16)
        self.collect()
        self.clock.return_value = self.week.cutoff_at-timedelta(minutes=15)
        self.collect()
        self.assertEqual(self.provider.call_count, 1)
        self.clock.return_value = self.week.cutoff_at-timedelta(minutes=11)
        self.collect()
        self.clock.return_value = self.week.cutoff_at-timedelta(minutes=6)
        self.collect()
        self.clock.return_value = self.week.cutoff_at-timedelta(minutes=1)
        self.collect()
        self.assertEqual(self.provider.call_count, 4)
        self.clock.return_value = self.week.cutoff_at
        self.collect()
        self.assertEqual(self.provider.call_count, 4)

    def test_failures_are_paced_and_preserve_missing_counters(self):
        self.provider.side_effect = ValueError('Unavailable test provider')
        self.collect()
        self.clock.return_value += timedelta(minutes=1)
        self.collect()
        self.assertEqual(self.provider.call_count, 1)
        snapshot = self.entry.snapshots.get()
        self.assertEqual(snapshot.status, 'error')
        self.assertIsNone(snapshot.likes)
        self.assertIsNone(snapshot.views)
        self.assertNotIn('Unavailable test provider', str(snapshot.provenance))

    def test_disabled_or_frozen_rounds_never_call_providers(self):
        with override_settings(LEAGUE_ENABLED=False):
            self.collect()
        for state in ('scheduled', 'finalizing', 'finalized', 'canceled', 'exhibition'):
            CompetitionWeek.objects.filter(pk=self.week.pk).update(state=state)
            self.collect()
        self.provider.assert_not_called()

    def test_response_completed_after_cutoff_is_audited_but_cannot_score(self):
        self.clock.return_value = self.week.cutoff_at-timedelta(seconds=1)
        def slow_response(*_):
            data = self.observation()
            self.clock.return_value = self.week.cutoff_at+timedelta(seconds=1)
            data['completed_at'] = self.clock.return_value
            return data
        self.provider.side_effect = slow_response
        self.collect()
        snapshot = self.entry.snapshots.get()
        self.assertTrue(snapshot.provenance['after_cutoff'])
        self.assertIsNone(services._closing_snapshot(self.entry, self.week, self.clock.return_value, final=True))

    def test_changed_provider_metadata_is_unavailable_not_reclassified(self):
        data = self.observation()
        data['video_format'] = 'long'
        self.provider.side_effect = None
        self.provider.return_value = data
        self.collect()
        snapshot = self.entry.snapshots.get()
        self.assertEqual(snapshot.video_format, 'short')
        self.assertEqual(snapshot.status, 'error')
        self.assertIsNone(snapshot.likes)

    def test_week_filter_scopes_collection(self):
        self.collect(week=self.week.pk+1)
        self.provider.assert_not_called()
