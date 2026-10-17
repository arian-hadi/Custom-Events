"""Website-history grading, with synthetic observations and no provider/SMTP I/O."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from edithub.league import services
from edithub.league.automation import automatic_version, upgrade_scheduled_grading
from edithub.league.scoring import automatic_config, score_cohort, validate_config, LeagueError
from edithub.league_models import CompetitionEntry, EntryBaseline, LeagueSettings, MetricSnapshot, ScoringVersion
from edithub.models import EditorApplication
from platform_api.league_views import result_row

START = datetime(2027, 1, 4, tzinfo=timezone.utc)


class WebsiteScoreTests(SimpleTestCase):
    def test_views_not_likes_and_debut_is_a_component_not_extra_points(self):
        config = automatic_config()
        rows = score_cohort(config, {1: (100, 1000, None), 2: (200, 4000, None), 3: (300, 3000, None)}, debut_ids={1, 2, 3})
        self.assertEqual([Decimal(row['popularity_score']) for row in rows.values()], [0, 100, 50])
        self.assertEqual([Decimal(row['response_score']) for row in rows.values()], [75, 0, 75])
        self.assertEqual([Decimal(row['weekly_score']) for row in rows.values()], [Decimal('63'), Decimal('45.5'), Decimal('73')])
        self.assertTrue(all(row['debut_bonus'] and not row['neutral_improvement'] for row in rows.values()))
        config['debut_improvement_score'] = '90'
        boosted = score_cohort(config, {1: (100, 1000, None)}, debut_ids={1})[1]
        self.assertEqual(Decimal(boosted['weekly_score']), 62)  # 25 + 27 + 10

    def test_five_editors_with_three_two_and_no_prior_edits(self):
        # Inputs are medians of their saved likes, not old scores or points.
        rows = score_cohort(automatic_config(), {
            1: (400, 4000, 200), 2: (300, 6000, 300),  # 3 earlier edits each
            3: (100, 2000, 200), 4: (600, 12000, 200),  # 2 earlier edits each
            5: (300, 3000, None),  # first week
        }, debut_ids={5})
        self.assertEqual([Decimal(rows[i]['relative_performance']) for i in range(1, 5)], [2, 1, Decimal('.5'), 3])
        self.assertEqual(Decimal(rows[4]['improvement_score']), 100)
        self.assertEqual(Decimal(rows[3]['improvement_score']), 0)
        self.assertEqual(Decimal(rows[5]['improvement_score']), 85)
        self.assertEqual(Decimal(rows[5]['weekly_score']), Decimal('74.25'))

    def test_ties_single_returning_editor_zero_baseline_and_invalid_config(self):
        rows = score_cohort(automatic_config(), {1: (100, 1000, 0), 2: (100, 1000, None)}, debut_ids={2})
        self.assertEqual(Decimal(rows[1]['relative_performance']), 5)
        self.assertEqual(Decimal(rows[1]['improvement_score']), 50)  # Only one measured ratio
        self.assertEqual(Decimal(rows[1]['popularity_score']), 50)
        for key, value in [('debut_improvement_score', 101), ('debut_improvement_score', 'NaN'), ('baseline_max_samples', 8), ('popularity_metric', 'likes')]:
            config = automatic_config()
            config[key] = value
            with self.subTest(key=key), self.assertRaises(LeagueError):
                validate_config(config)


@override_settings(LEAGUE_ENABLED=True)
class WebsiteHistoryTests(TestCase):
    def setUp(self):
        self.editor = get_user_model().objects.create_user(username='website-editor', email='website@example.test', is_verified=True)
        self.admin = get_user_model().objects.create_user(username='grading-admin', email='grading-admin@example.test', is_staff=True, is_superuser=True)
        self.options = LeagueSettings.objects.create(enabled=True, minimum_entries=1)
        self.version = automatic_version(self.options, now=START - timedelta(weeks=10))

    def entry(self, start, *, video=None, key=None, platform='youtube'):
        week = services.ensure_week(start, self.version)
        video = video or f'edit{week.pk}'
        return CompetitionEntry.objects.create(week=week, editor=self.editor, platform=platform, video_id=video,
            channel_id='test-channel', video_format='short', published_at=start - timedelta(days=180),
            canonical_url=f'https://example.test/{video}', content_key=key or f'{platform}:{video}')

    def observe(self, entry, likes, views=10000, completed=None):
        completed = completed or entry.week.cutoff_at - timedelta(minutes=1)
        with patch('edithub.league.services.timezone.now', return_value=completed):
            return services.record_snapshot(entry, dict(likes=likes, views=views, completed_at=completed, provider='isolated-test'))

    def finish(self, start, likes=100, **kwargs):
        entry = self.entry(start, **kwargs)
        services.activate_week(entry.week, now=start)
        self.observe(entry, likes)
        services.finalize_week(entry.week, now=entry.week.cutoff_at)
        return entry

    def test_available_one_to_five_results_and_latest_five_median(self):
        entries = []
        for index, count in enumerate([10, 20, 30, 40, 50, 60, 70]):
            entry = self.finish(START - timedelta(weeks=6-index), likes=count)
            baseline = entry.baseline
            self.assertEqual(baseline.sample_count, min(index, 5))
            self.assertEqual(baseline.is_debut, index == 0)
            if index:
                previous = [10 * (i + 1) for i in range(max(0, index-5), index)]
                self.assertEqual(Decimal(baseline.median_likes), Decimal(sum(previous)) / len(previous))
                self.assertEqual(baseline.source_result_ids, [item.results.get().pk for item in entries[-5:][::-1]])
            entries.append(entry)
        # Crossed month and year; seven league awards, never a repeated debut.
        self.assertEqual(EntryBaseline.objects.filter(is_debut=True).count(), 1)
        before = list(entries[-1].results.values())
        services.finalize_week(entries[-1].week, now=entries[-1].week.cutoff_at + timedelta(days=1))
        self.assertEqual(list(entries[-1].results.values()), before)
        self.assertEqual(entries[-1].points_awards.count(), 1)

    def test_frozen_website_counters_ignore_channel_history_and_later_engagement(self):
        previous = self.finish(START - timedelta(weeks=1), likes=120)
        self.observe(previous, 9999, completed=START - timedelta(hours=1))  # after its cutoff
        MetricSnapshot.objects.create(editor=self.editor, platform='youtube', video_id='not-submitted', channel_id='test-channel',
            video_format='short', published_at=START-timedelta(days=180), requested_at=START-timedelta(days=1),
            completed_at=START-timedelta(days=1), received_at=START-timedelta(days=1), status='success', provider='isolated-test', likes=999999, views=9999999)
        current = self.entry(START, platform='tiktok')
        services.activate_week(current.week, now=START)
        self.assertEqual(current.baseline.sample_count, 1)
        self.assertEqual(Decimal(current.baseline.median_likes), 120)
        self.assertFalse(current.baseline.is_debut)
        self.assertEqual(current.baseline.sample_ids, [previous.results.get().snapshot_id])

    def test_repeated_edit_in_different_months_supplies_only_latest_history_sample(self):
        self.finish(START-timedelta(weeks=9), likes=100, video='repeated')
        unique = self.finish(START-timedelta(weeks=6), likes=50)
        newest = self.finish(START-timedelta(weeks=5), likes=300, video='repeated')
        current = self.entry(START)
        services.activate_week(current.week, now=START)
        self.assertEqual(current.baseline.source_result_ids, [newest.results.get().pk, unique.results.get().pk])
        self.assertEqual(Decimal(current.baseline.median_likes), 175)

    def test_history_uses_revision_known_at_start_even_if_activation_delayed(self):
        previous = self.finish(START - timedelta(weeks=1), likes=120)
        original = previous.results.get()
        services.correct_week(previous.week, actor=self.admin, reason='Later moderation',
            disqualified_entry_ids=[previous.pk], now=START + timedelta(hours=1))
        current = self.entry(START)
        services.activate_week(current.week, now=START + timedelta(hours=2))
        self.assertEqual(current.baseline.source_result_ids, [original.pk])
        self.assertEqual(Decimal(current.baseline.median_likes), 120)

    def test_disqualification_known_before_start_excludes_history_without_renewing_debut(self):
        previous = self.finish(START - timedelta(weeks=1), likes=120)
        services.correct_week(previous.week, actor=self.admin, reason='Prior moderation',
            disqualified_entry_ids=[previous.pk], now=START-timedelta(hours=1))
        current = self.finish(START)
        self.assertEqual(current.baseline.sample_count, 0)
        self.assertFalse(current.baseline.is_debut)
        self.assertEqual(Decimal(current.results.get().improvement_score), 50)

    def test_unfinalized_history_cannot_be_used_or_renew_debut(self):
        previous = self.entry(START - timedelta(weeks=1))
        services.activate_week(previous.week, now=previous.week.start_at)
        self.observe(previous, 9999)
        current = self.finish(START)
        self.assertEqual(current.baseline.sample_count, 0)
        self.assertFalse(current.baseline.is_debut)

    def test_exhibition_is_real_experience_and_same_edit_crosspost_is_excluded(self):
        config = automatic_config()
        config['minimum_entries'] = 5
        self.version = ScoringVersion.objects.create(name='exhibition-website', config=config, rules_confirmed=True)
        previous = self.finish(START-timedelta(weeks=2), likes=120, key='shared-edit')
        previous.week.refresh_from_db()
        self.assertEqual(previous.week.state, 'exhibition')
        current = self.entry(START, key='shared-edit', platform='tiktok')
        services.activate_week(current.week, now=START)
        self.assertFalse(current.baseline.is_debut)
        self.assertEqual(current.baseline.sample_count, 0)
        later = self.entry(START + timedelta(weeks=1))
        services.activate_week(later.week, now=later.week.start_at)
        self.assertEqual(later.baseline.sample_count, 1)

    def test_api_discloses_debut_and_views_and_preserves_frozen_scores(self):
        entry = self.entry(START)
        services.activate_week(entry.week, now=START)
        self.observe(entry, 250)
        now = entry.week.cutoff_at - timedelta(seconds=20)
        with patch('platform_api.league_views.timezone.now', return_value=now):
            self.client.force_login(self.editor)
            live = self.client.get('/api/v2/league/standings/', {'week': entry.week_id}).json()['rows'][0]
            own = self.client.get('/api/v2/league/entries/me/').json()['entries'][0]
        for row in [live, own]:
            self.assertTrue(row['debut_bonus'])
            self.assertEqual(row['popularity_metric'], 'views')
            self.assertFalse(row['neutral_baseline'])
            self.assertEqual(row['improvement_score'], '85')
        services.finalize_week(entry.week, now=entry.week.cutoff_at)
        frozen = result_row(entry.results.get())
        self.assertEqual(frozen['weekly_score'], live['weekly_score'])
        self.assertTrue(frozen['debut_bonus'])
        self.assertEqual(frozen['points'], 25)
        self.options.debut_improvement_score = 90
        self.options.save()
        self.observe(entry, 800, completed=entry.week.cutoff_at + timedelta(days=1))
        self.assertEqual(result_row(entry.results.get()), frozen)

    def test_legacy_result_keeps_likes_label_and_no_debut(self):
        config = automatic_config()
        config.update(mapping_policy='round_cohort_v1', baseline_policy='channel_age_matched', popularity_metric='likes', baseline_min_samples=5, baseline_max_samples=8, minimum_entries=1)
        self.version = ScoringVersion.objects.create(name='legacy-website-test', config=config, rules_confirmed=True)
        entry = self.finish(START)
        row = result_row(entry.results.get())
        self.assertEqual(row['popularity_metric'], 'likes')
        self.assertFalse(row['debut_bonus'])
        self.assertEqual(Decimal(row['weekly_score']), 50)

    def test_audited_upgrade_only_changes_future_round_rules(self):
        entry = self.entry(START)
        old = entry.week.scoring_version_id
        self.options.debut_improvement_score = 90
        self.options.save()
        upgraded = upgrade_scheduled_grading(entry.week, actor=self.admin, reason='Approved prospective rules', now=START-timedelta(hours=1))
        self.assertNotEqual(upgraded.scoring_version_id, old)
        self.assertEqual(upgraded.scoring_version.config['debut_improvement_score'], '90')
        upgrade_scheduled_grading(upgraded, actor=self.admin, reason='Retry', now=START-timedelta(hours=1))
        self.assertEqual(LogEntry.objects.filter(object_id=str(entry.week_id)).count(), 1)
        with self.assertRaises(LeagueError):
            upgrade_scheduled_grading(upgraded, actor=self.admin, reason='Too late', now=START)
        with self.assertRaises(LeagueError):
            upgrade_scheduled_grading(upgraded, actor=self.editor, reason='Unauthorized', now=START-timedelta(hours=1))

    def test_history_worker_never_discovers_channel_videos_for_new_scoring(self):
        entry = self.entry(START)
        app = EditorApplication(user=self.editor, channel_type='youtube', channel_link='https://youtube.com/@test', status='accepted', channel_verified=True)
        EditorApplication.objects.bulk_create([app])
        CompetitionEntry.objects.filter(pk=entry.pk).update(approved_application=app)
        with patch('edithub.management.commands.league_history.timezone.now', return_value=START-timedelta(days=1)), patch('edithub.management.commands.league_history.approved_channel_context') as provider:
            call_command('league_history', stdout=StringIO())
        provider.assert_not_called()

    def test_admin_can_roll_future_rules_forward_with_required_audit_reason(self):
        entry = self.entry(START)
        old = entry.week.scoring_version_id
        self.options.debut_improvement_score = 90
        self.options.save()
        url = f'/admin/edithub/competitionweek/{entry.week_id}/operations/'
        with patch('edithub.league.automation.timezone.now', return_value=START-timedelta(days=1)):
            self.client.force_login(self.admin)
            response = self.client.post(url, {'operation': 'upgrade_grading'})
            self.assertContains(response, 'An audit reason is required.')
            entry.week.refresh_from_db()
            self.assertEqual(entry.week.scoring_version_id, old)
            response = self.client.post(url, {'operation': 'upgrade_grading', 'reason': 'Adopt new scoring before start'})
        self.assertEqual(response.status_code, 302)
        entry.week.refresh_from_db()
        self.assertNotEqual(entry.week.scoring_version_id, old)
        self.assertTrue(LogEntry.objects.filter(user=self.admin, change_message__startswith='Grading version', object_id=str(entry.week_id)).exists())
