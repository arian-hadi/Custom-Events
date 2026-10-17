"""League HTTP acceptance tests; isolated database and no provider/SMTP calls."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from edithub.league.calendar import monday_for, next_week_start
from edithub.league.providers import ProviderError, canonical_video
from edithub.league.scoring import default_config
from edithub.league_models import (
    CompetitionEntry, CompetitionWeek, LeagueSeason, MetricSnapshot, MonthlyAward,
    ScoringVersion, WeeklyResult,
)
from edithub.models import EditorApplication


NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
VIDEO = 'AbCdEfGhI_1'
OTHER_VIDEO = 'AbCdEfGhI_2'
CHANNEL = 'UC' + 'A' * 22
BASE = '/api/v2/league/'


def calibrated_test_config():
    """Synthetic reference fixtures only; never suitable for a real season."""
    config = default_config()
    config['supported_formats'] = ['youtube:short', 'tiktok:video']
    for supported in config['supported_formats']:
        for band in config['age_bands']:
            config['references'][f"{supported}:{band['key']}"] = {
                'prior_rate': '0.05', 'prior_views': '1000', 'baseline_floor': '10', 'improvement_cap': '5',
                'response': [['0', '0'], ['1', '100']], 'improvement': [['0', '0'], ['5', '100']],
                'popularity': [['0', '0'], ['10000', '100']],
            }
    return config


@override_settings(LEAGUE_ENABLED=True, ADMIN_EMAIL_SEND_IMMEDIATELY=False)
class LeagueAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email='league-member@example.test', username='league-member', is_verified=True)
        cls.other = User.objects.create_user(email='league-other@example.test', username='league-other', is_verified=True)
        cls.season = LeagueSeason.objects.create(year=2026)
        cls.version = ScoringVersion.objects.create(name='api-fixture-only', config=calibrated_test_config(),
            rules_confirmed=True, calibrated=True, calibration_notes='Synthetic isolated test fixtures.')
        # Skip legacy application signals: these fixtures are already reviewed.
        cls.application = EditorApplication(user=cls.member, channel_type='youtube',
            channel_link=f'https://www.youtube.com/channel/{CHANNEL}', channel_name='Creator',
            editing_area='transformers', status='accepted', channel_verified=True, data_consent=True)
        EditorApplication.objects.bulk_create([cls.application])

    def setUp(self):
        cache.clear()
        clock = patch('platform_api.league_views.timezone.now', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        provider = patch('platform_api.league_views.fetch_verified_video', side_effect=self.observation)
        self.provider = provider.start()
        self.addCleanup(provider.stop)
        self.client.force_login(self.member)
        self.upcoming = self.week(next_week_start(NOW))

    def week(self, start, **changes):
        values = dict(season=self.season, scoring_version=self.version, start_at=start,
            cutoff_at=start + timedelta(days=5), scoring_date=(start + timedelta(days=4)).date())
        values.update(changes)
        return CompetitionWeek.objects.create(**values)

    def observation(self, application=None, url=f'https://youtu.be/{VIDEO}'):
        platform, video_id, canonical = canonical_video(url)
        return dict(platform=platform, video_id=video_id, canonical_url=canonical,
            channel_id=CHANNEL, video_format='short', published_at=NOW - timedelta(days=400),
            title='An older edit', requested_at=NOW - timedelta(seconds=1), completed_at=NOW,
            likes=8200, views=100000, provider='mock_provider', status='success', provenance={'counter_scope': 'lifetime'})

    def submit(self, **changes):
        values = dict(approved_application_id=self.application.pk, video_url=f'https://youtu.be/{VIDEO}')
        values.update(changes)
        return self.client.post(BASE + 'entries/', values, content_type='application/json')

    def entry(self, week=None, user=None, video_id=VIDEO, **changes):
        values = dict(week=week or self.upcoming, editor=user or self.member, approved_application=self.application,
            platform='youtube', video_id=video_id, canonical_url=f'https://www.youtube.com/watch?v={video_id}',
            channel_id=CHANNEL, video_format='short', published_at=NOW-timedelta(days=400), state='queued')
        values.update(changes)
        return CompetitionEntry.objects.create(**values)

    def test_next_week_intake_counts_existing_engagement_and_ignores_client_scores(self):
        response = self.submit(likes=0, views=0, weekly_score=100, state='active',
            editor_id=self.other.pk, week_id=999, content_key='browser-key', video_format='long')
        self.assertEqual(response.status_code, 201, response.content)
        entry = CompetitionEntry.objects.get()
        self.assertEqual((entry.editor_id, entry.week_id, entry.state), (self.member.pk, self.upcoming.pk, 'queued'))
        self.assertEqual(entry.content_key, 'youtube:' + VIDEO)
        self.assertEqual(entry.video_format, 'short')
        self.assertEqual(entry.snapshots.get().likes, 8200)
        self.assertEqual(entry.published_at, NOW-timedelta(days=400))
        self.assertEqual(WeeklyResult.objects.count(), 0)

    def test_disabled_or_unconfirmed_or_uncalibrated_rules_prevent_provider_calls(self):
        with override_settings(LEAGUE_ENABLED=False):
            self.assertEqual(self.submit().status_code, 409)
            self.assertFalse(self.client.get(BASE+'status/').json()['can_submit'])
        for changes in ({'rules_confirmed': False}, {'calibrated': False}, {'calibration_notes': ''}, {'config': default_config()}):
            with self.subTest(changes=changes):
                ScoringVersion.objects.filter(pk=self.version.pk).update(**changes)
                self.assertEqual(self.submit().status_code, 409)
                self.assertFalse(self.client.get(BASE+'status/').json()['configuration_ready'])
                ScoringVersion.objects.filter(pk=self.version.pk).update(rules_confirmed=True, calibrated=True,
                    calibration_notes='Synthetic isolated fixtures', config=calibrated_test_config())
        self.provider.assert_not_called()

    def test_anonymous_unverified_and_csrf_requests_cannot_submit(self):
        self.client.logout()
        self.assertEqual(self.submit().status_code, 401)
        self.member.is_verified = False
        self.member.save(update_fields=['is_verified'])
        self.client.force_login(self.member)
        self.assertEqual(self.submit().status_code, 401)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.other)
        self.assertEqual(csrf_client.post(BASE+'entries/', {}, content_type='application/json').status_code, 403)
        self.provider.assert_not_called()

    def test_other_unapproved_unverified_or_removing_channels_are_not_eligible(self):
        for changes in ({'user_id': self.other.pk}, {'status': 'pending'}, {'channel_verified': False}, {'removal_requested': True}):
            with self.subTest(changes=changes):
                EditorApplication.objects.filter(pk=self.application.pk).update(**changes)
                self.assertEqual(self.submit().status_code, 404)
                EditorApplication.objects.filter(pk=self.application.pk).update(user=self.member, status='accepted', channel_verified=True, removal_requested=False)
        self.provider.assert_not_called()

    def test_original_work_checkbox_is_not_required_and_cannot_bypass_duplicates(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(self.submit(original_edit_confirmed=True).status_code, 409)
        self.assertEqual(self.submit(original_edit_confirmed=False).status_code, 409)
        self.assertEqual(CompetitionEntry.objects.count(), 1)

    def test_canonical_variants_and_second_platform_cannot_create_second_round_entry(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(self.submit(video_url=f'https://youtube.com/shorts/{VIDEO}').status_code, 409)
        self.assertEqual(self.submit(video_url=f'https://youtu.be/{OTHER_VIDEO}').status_code, 409)
        self.assertEqual(CompetitionEntry.objects.count(), 1)
        self.assertEqual(MetricSnapshot.objects.count(), 1)

    def test_video_that_competed_in_same_month_cannot_be_reentered(self):
        prior = self.week(monday_for(NOW), state='finalized')
        self.entry(week=prior, state='active')
        self.assertEqual(self.submit().status_code, 409)
        self.assertFalse(self.upcoming.entries.exists())

    def test_reviewed_crosspost_identity_prevents_repeat_result(self):
        prior = self.week(monday_for(NOW), state='finalized')
        self.entry(week=prior, video_id=OTHER_VIDEO, content_key='reviewed:original-edit-1', state='active')
        observation = self.observation()
        observation['content_key'] = 'reviewed:original-edit-1'
        self.provider.side_effect = None
        self.provider.return_value = observation
        self.assertEqual(self.submit().status_code, 409)

    def test_previous_months_edit_is_eligible_and_old_entry_remains_unchanged(self):
        prior = self.week(monday_for(NOW)-timedelta(days=7), state='finalized')
        original = self.entry(week=prior, state='active')
        old_values = CompetitionEntry.objects.filter(pk=original.pk).values().get()
        response = self.submit(video_url=f'https://youtube.com/shorts/{VIDEO}', competition_month='1999-01-01')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CompetitionEntry.objects.filter(pk=original.pk).values().get(), old_values)
        entry = CompetitionEntry.objects.get(week=self.upcoming)
        self.assertEqual(str(entry.competition_month), '2026-10-01')
        self.assertEqual(str(original.competition_month), '2026-09-01')
        self.assertEqual(response.json()['entry']['week']['competition_month'], '2026-10')

    def test_unclassified_or_uncalibrated_format_is_rejected_before_it_can_block_round(self):
        for value in ('unknown', 'video', 'long'):
            observation = self.observation()
            observation['video_format'] = value
            self.provider.side_effect = None
            self.provider.return_value = observation
            response = self.submit()
            self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(CompetitionEntry.objects.exists())

    def test_replace_is_atomic_and_preserves_original_on_duplicate_or_provider_failure(self):
        old = self.entry()
        other = self.week(monday_for(NOW), state='finalized')
        self.entry(week=other, video_id=OTHER_VIDEO, state='active')
        data = {'approved_application_id': self.application.pk, 'video_url': f'https://youtu.be/{OTHER_VIDEO}', 'original_edit_confirmed': True}
        url = BASE+f'entries/{old.pk}/replace/'
        self.assertEqual(self.client.post(url, data, content_type='application/json').status_code, 409)
        old.refresh_from_db()
        self.assertEqual(old.state, 'queued')
        self.provider.side_effect = ProviderError('provider_unavailable', 'Provider temporarily unavailable.', retryable=True)
        self.assertEqual(self.client.post(url, data, content_type='application/json').status_code, 503)
        old.refresh_from_db()
        self.assertEqual(old.state, 'queued')

    def test_replace_changes_only_the_owners_queued_entry(self):
        old = self.entry()
        data = {'approved_application_id': self.application.pk, 'video_url': f'https://youtu.be/{OTHER_VIDEO}', 'original_edit_confirmed': True}
        url = BASE+f'entries/{old.pk}/replace/'
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, data, content_type='application/json').status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url, data, content_type='application/json').status_code, 201)
        old.refresh_from_db()
        self.assertEqual(old.state, 'withdrawn')
        self.assertEqual(self.upcoming.entries.get(state='queued').video_id, OTHER_VIDEO)

    def test_deadline_and_channel_rights_are_rechecked_after_provider_io(self):
        def revoked(application, url):
            EditorApplication.objects.filter(pk=application.pk).update(removal_requested=True)
            return self.observation(application, url)
        self.provider.side_effect = revoked
        self.assertEqual(self.submit().status_code, 404)
        EditorApplication.objects.filter(pk=self.application.pk).update(removal_requested=False)
        def changed(application, url):
            EditorApplication.objects.filter(pk=application.pk).update(channel_link='https://youtube.com/@different')
            return self.observation(application, url)
        self.provider.side_effect = changed
        self.assertEqual(self.submit().status_code, 409)
        self.assertFalse(CompetitionEntry.objects.exists())

    def test_provider_response_arriving_at_monday_is_not_late_intake(self):
        with patch('platform_api.league_views.timezone.now', return_value=NOW) as clock:
            def completed_on_monday(application, url):
                clock.return_value = self.upcoming.start_at
                return self.observation(application, url)
            self.provider.side_effect = completed_on_monday
            self.assertEqual(self.submit().status_code, 400)
        self.assertFalse(CompetitionEntry.objects.exists())

    def test_withdraw_is_private_and_locked_at_activation_even_if_scheduler_is_late(self):
        entry = self.entry()
        url = BASE+f'entries/{entry.pk}/withdraw/'
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {}, content_type='application/json').status_code, 404)
        self.client.force_login(self.member)
        with patch('platform_api.league_views.timezone.now', return_value=self.upcoming.start_at):
            self.assertEqual(self.client.post(url, {}, content_type='application/json').status_code, 409)
        with override_settings(LEAGUE_ENABLED=False):
            item = self.client.get(BASE+'entries/me/').json()['entries'][0]
            self.assertTrue(item['can_withdraw'])
            self.assertFalse(item['can_replace'])
            self.assertEqual(self.client.post(url, {}, content_type='application/json').status_code, 200)

    def test_queued_entries_are_private_and_user_listing_is_scoped(self):
        entry = self.entry()
        self.entry(user=self.other, video_id=OTHER_VIDEO)
        own = self.client.get(BASE+'entries/me/').json()['entries']
        self.assertEqual([row['id'] for row in own], [entry.pk])
        self.client.logout()
        self.assertEqual(self.client.get(BASE+'entries/me/').status_code, 401)
        self.assertEqual(self.client.get(BASE+'standings/', {'week': self.upcoming.pk}).json()['rows'], [])
        calendar = self.client.get(BASE+'rounds/').json()['rounds']
        self.assertEqual(calendar[0]['entry_count'], 0)
        self.assertNotIn(VIDEO, str(calendar))

    def test_finalized_standings_and_winner_use_effective_revision_and_placed_entries(self):
        week = self.week(monday_for(NOW), state='finalized', current_revision=2)
        entry = self.entry(week=week, state='active')
        rejected = self.entry(week=week, user=self.other, video_id=OTHER_VIDEO, state='disqualified')
        WeeklyResult.objects.create(week=week, entry=entry, revision=1, placement=1, is_winner=True, league_points=25, weekly_score='99')
        WeeklyResult.objects.create(week=week, entry=entry, revision=2, placement=1, is_winner=True, league_points=25, weekly_score='70')
        WeeklyResult.objects.create(week=week, entry=rejected, revision=2, placement=None, is_winner=False)
        rows = self.client.get(BASE+'standings/').json()['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['weekly_score'], '70')
        winners = self.client.get(BASE+'winners/').json()
        self.assertEqual(winners['weekly_winner']['weekly_score'], '70')
        self.assertIsNone(winners['monthly_winner'])
        MonthlyAward.objects.create(year=2026, month=9, revision=1, editor=self.member, entry=entry, points=72)
        self.assertEqual(self.client.get(BASE+'winners/').json()['monthly_winner']['points'], 72)

    def test_exhibition_or_canceled_rounds_never_publish_official_winners(self):
        week = self.week(monday_for(NOW), state='exhibition', current_revision=1)
        entry = self.entry(week=week, state='active')
        WeeklyResult.objects.create(week=week, entry=entry, revision=1, placement=1, is_winner=True, league_points=0)
        for state in ('exhibition', 'canceled'):
            CompetitionWeek.objects.filter(pk=week.pk).update(state=state)
            self.assertEqual(self.client.get(BASE+'standings/').json()['rows'], [])
            self.assertIsNone(self.client.get(BASE+'winners/').json()['weekly_winner'])

    def test_malformed_public_query_parameters_are_json_errors(self):
        for route, data in (('rounds/', {'year': 'bad'}), ('standings/', {'period': 'month', 'month': '13'}),
                ('standings/', {'period': 'invalid'}), ('standings/', {'week': 'invalid'})):
            response = self.client.get(BASE+route, data)
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.json())

    def test_table_and_winner_reuse_granted_titles_without_affecting_frozen_result(self):
        from edithub.models import EditorTitle, UserTitleUnlock
        title = EditorTitle.objects.create(name='Legacy champion', rarity='legendary', unlock_method='manual')
        get_user_model().objects.filter(pk=self.member.pk).update(selected_title=title)
        week = self.week(monday_for(NOW), state='finalized', current_revision=1)
        entry = self.entry(week=week, state='active')
        result = WeeklyResult.objects.create(week=week, entry=entry, revision=1, placement=1,
            is_winner=True, league_points=25, weekly_score='70')
        self.assertEqual(self.client.get(BASE+'standings/').json()['rows'][0]['editor_title'], '')
        UserTitleUnlock.objects.create(user=self.member, title=title)
        row = self.client.get(BASE+'standings/').json()['rows'][0]
        self.assertEqual((row['editor_title'], row['editor_title_rarity']), ('Legacy champion', 'legendary'))
        self.assertEqual(self.client.get(BASE+'winners/').json()['weekly_winner']['editor_title_rarity'], 'legendary')
        result.refresh_from_db()
        self.assertEqual((result.placement, result.league_points, result.weekly_score), (1, 25, '70'))
        EditorTitle.objects.filter(pk=title.pk).update(is_active=False)
        self.assertIsNone(self.client.get(BASE+'standings/').json()['rows'][0]['editor_title_rarity'])

    def test_calendar_month_choices_include_history_and_current_but_not_future(self):
        self.week(monday_for(NOW)-timedelta(days=28), state='finalized')
        self.week(monday_for(NOW)+timedelta(days=42))
        data = self.client.get(BASE+'rounds/').json()
        self.assertEqual(data['months'], [{'month': 10, 'label': 'October 2026'}, {'month': 9, 'label': 'September 2026'}])
        self.assertEqual(self.client.get(BASE+'rounds/', {'year': 2025}).json()['months'], [])
