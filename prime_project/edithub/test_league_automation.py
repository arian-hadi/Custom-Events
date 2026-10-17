"""Automatic league acceptance with synthetic metrics and an isolated database."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings

from edithub.league.automation import league_enabled, prepare_rounds
from edithub.league.scoring import automatic_config, score_cohort, version_ready, DataPending
from edithub.league import services
from edithub.league_models import LeagueSettings, CompetitionWeek, CompetitionEntry, ScoringVersion, LeaguePointsAward, MonthlyAward
from edithub.models import EditorApplication

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


class AutomaticScoringTests(SimpleTestCase):
    def test_real_cohort_components_weights_and_missing_history(self):
        legacy = automatic_config()
        legacy['mapping_policy'] = 'round_cohort_v1'
        rows = score_cohort(legacy, {1: (100, 1000, None), 2: (200, 1000, None), 3: (300, 1000, None)})
        self.assertEqual([Decimal(row['weekly_score']) for row in rows.values()], [15, 50, 85])
        self.assertTrue(rows[1]['neutral_improvement'])
        self.assertEqual(rows[3]['likes'], '300')
        self.assertEqual(rows[3]['cohort_size'], 3)

    def test_tied_components_and_real_creator_baselines(self):
        rows = score_cohort(automatic_config(), {1: (100, 1000, 50), 2: (100, 1000, 100)})
        self.assertEqual(Decimal(rows[1]['response_score']), 50)
        self.assertEqual(Decimal(rows[1]['popularity_score']), 50)
        self.assertEqual(Decimal(rows[1]['improvement_score']), 100)
        self.assertEqual(Decimal(rows[2]['improvement_score']), 0)
        self.assertEqual(Decimal(score_cohort(automatic_config(), {1: (0, 0, None)})[1]['weekly_score']), 50)
        for counters in [(None, 5, None), (1, None, None), (1, 0, None)]:
            with self.assertRaises(DataPending):
                score_cohort(automatic_config(), {1: counters})


@override_settings(LEAGUE_ENABLED=False)
class AutomaticLeagueTests(TestCase):
    def setUp(self):
        self.options = LeagueSettings.objects.create(enabled=True)

    def test_prepares_four_future_rounds_and_retries_without_backfilling(self):
        first = prepare_rounds(NOW)
        self.assertEqual(len(first), 4)
        self.assertEqual(first[0].start_at.isoformat(), '2026-10-12T00:00:00+00:00')
        prepare_rounds(NOW)
        self.assertEqual(CompetitionWeek.objects.count(), 4)
        self.assertEqual(ScoringVersion.objects.count(), 1)
        self.assertTrue(version_ready(first[0].scoring_version))
        self.assertFalse(first[0].scoring_version.calibrated)
        prepare_rounds(NOW + timedelta(weeks=1))
        self.assertEqual(CompetitionWeek.objects.count(), 5)

    def test_admin_switch_overrides_env_and_new_points_do_not_rewrite_existing_rounds(self):
        original = prepare_rounds(NOW)[0].scoring_version
        self.options.placement_points[0] = 30
        self.options.save()
        prepare_rounds(NOW + timedelta(weeks=1))
        original.refresh_from_db()
        self.assertEqual(original.config['placement_points'][0], 25)
        self.assertEqual(CompetitionWeek.objects.latest('start_at').scoring_version.config['placement_points'][0], 30)
        self.options.enabled = False
        self.options.save()
        with override_settings(LEAGUE_ENABLED=True):
            self.assertFalse(league_enabled())
            self.assertEqual(prepare_rounds(NOW), [])

    def test_bad_weights_rejected(self):
        self.options.response_weight = 99
        with self.assertRaises(ValidationError):
            self.options.save()

    def test_calendar_rolls_into_next_year_without_reopening(self):
        weeks = prepare_rounds(datetime(2026, 12, 27, tzinfo=timezone.utc))
        self.assertEqual(weeks[0].start_at.year, 2026)
        self.assertEqual(weeks[0].scoring_date.isoformat(), '2027-01-01')
        self.assertEqual(weeks[0].season.year, 2027)
        self.assertTrue(league_enabled())

    def test_admin_simple_form_opens_without_json_and_is_audited(self):
        admin = get_user_model().objects.create_user(username='operator', email='operator@example.test', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        url = '/admin/edithub/leaguesettings/1/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Place 1 points')
        self.assertNotContains(response, 'name="placement_points"')
        data = dict(enabled='on', response_weight=50, improvement_weight=30, popularity_weight=20, debut_improvement_score=85, minimum_entries=5, finisher_points=2, _save='Save')
        data.update({f'place_{index}': value for index, value in enumerate(self.options.placement_points, 1)})
        with patch('edithub.league.automation.timezone.now', return_value=NOW):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content)
        self.assertEqual(CompetitionWeek.objects.count(), 4)
        self.assertTrue(LogEntry.objects.filter(user=admin, object_id='1').exists())

    def test_intake_accepts_provider_native_youtube_format_then_automatic_week_and_month(self):
        week = prepare_rounds(NOW)[0]
        users = []
        for index in range(5):
            user = get_user_model().objects.create_user(username=f'auto{index}', email=f'auto{index}@example.test', is_verified=True)
            users.append(user)
            application = EditorApplication(user=user, channel_type='youtube', channel_link='https://www.youtube.com/@fixture', status='accepted', channel_verified=True, editing_area='transformers')
            EditorApplication.objects.bulk_create([application])
            self.client.force_login(user)
            observation = dict(platform='youtube', video_id=f'fixture{index}', channel_id='fixture', video_format='unknown',
                published_at=NOW - timedelta(days=100), canonical_url=f'https://www.youtube.com/watch?v=fixture{index}',
                title='Older edit', likes=100, views=1000, completed_at=NOW, provider='isolated-test')
            with patch('platform_api.league_views.timezone.now', return_value=NOW), patch('platform_api.league_views.fetch_verified_video', return_value=observation):
                response = self.client.post('/api/v2/league/entries/', {'approved_application_id': application.pk, 'video_url': observation['canonical_url'], 'original_edit_confirmed': True}, content_type='application/json')
            self.assertEqual(response.status_code, 201, response.content)
        with patch('edithub.league.services.timezone.now', return_value=week.start_at):
            call_command('league_tick', verbosity=0)
        for index, entry in enumerate(CompetitionEntry.objects.filter(week=week).order_by('pk')):
            closing = week.cutoff_at - timedelta(minutes=1)
            with patch('edithub.league.services.timezone.now', return_value=closing):
                services.record_snapshot(entry, dict(likes=100 * (index + 1), views=1000, completed_at=closing, provider='isolated-test'))
        with patch('edithub.league.services.timezone.now', return_value=week.cutoff_at):
            call_command('league_tick', verbosity=0)
            call_command('league_tick', verbosity=0)
        week.refresh_from_db()
        self.assertEqual(week.state, 'finalized')
        self.assertEqual(week.results.filter(is_winner=True).count(), 1)
        self.assertEqual(list(week.results.order_by('placement').values_list('league_points', flat=True)), [25, 20, 16, 13, 11])
        self.assertEqual(LeaguePointsAward.objects.count(), 5)
        # Other prepared October weeks represent genuine scheduled competitions;
        # resolve empty ones normally before the month can finish.
        for other in CompetitionWeek.objects.exclude(pk=week.pk).filter(scoring_date__month=10):
            services.activate_week(other, now=other.start_at)
            services.finalize_week(other, now=other.cutoff_at)
        month_end = datetime(2026, 11, 1, tzinfo=timezone.utc)
        with patch('edithub.league.services.timezone.now', return_value=month_end):
            call_command('league_tick', verbosity=0)
        award = MonthlyAward.objects.get(year=2026, month=10, effective=True)
        self.assertEqual(award.points, 25)
        self.assertEqual(award.editor_id, users[-1].pk)
        with patch('platform_api.league_views.timezone.now', return_value=month_end):
            self.assertIsNotNone(self.client.get('/api/v2/league/winners/').json()['monthly_winner'])
