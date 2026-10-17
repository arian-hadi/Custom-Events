"""Monthly repeat-entry guards and historical backfill; no provider or mail I/O."""
from datetime import datetime, timedelta, timezone
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from edithub.league.services import ensure_week
from edithub.league_models import CompetitionEntry, LeaguePointsAward, ScoringVersion, WeeklyResult
from edithub.test_league_core import fixture_config

UTC = timezone.utc


class MonthlyEntryIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(email='monthly-identity@example.test', username='monthly-identity')
        cls.version = ScoringVersion.objects.create(name='monthly-identity-fixture', config=fixture_config(),
            rules_confirmed=True, calibrated=True, calibration_notes='Synthetic test fixture only.')

    def week(self, year, month, day):
        return ensure_week(datetime(year, month, day, tzinfo=UTC), self.version)

    def entry(self, week, **changes):
        values = dict(week=week, editor=self.member, platform='youtube', video_id='AbCdEfGhI_1', channel_id='owner',
            published_at=week.start_at-timedelta(days=400), canonical_url='https://youtu.be/AbCdEfGhI_1')
        values.update(changes)
        return CompetitionEntry.objects.create(**values)

    def test_database_rejects_same_video_in_another_week_of_the_month(self):
        self.entry(self.week(2026, 9, 28))  # Friday October 2, not September.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(self.week(2026, 10, 5), content_key='different-key')

    def test_known_crosspost_cannot_bypass_monthly_content_constraint(self):
        self.entry(self.week(2026, 10, 5), content_key='reviewed:shared-edit')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(self.week(2026, 10, 12), platform='tiktok', video_id='1234567890', content_key='reviewed:shared-edit')

    def test_withdrawal_releases_identity_but_disqualification_does_not(self):
        old = self.entry(self.week(2026, 10, 5), state='withdrawn')
        entry = self.entry(self.week(2026, 10, 12), state='disqualified')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(self.week(2026, 10, 19))
        self.assertEqual(old.content_key, entry.content_key)

    def test_weekend_in_next_month_does_not_change_friday_attribution(self):
        july = self.entry(self.week(2026, 7, 27))  # Saturday August 1 cutoff.
        august = self.entry(self.week(2026, 8, 3))
        self.assertEqual(str(july.competition_month), '2026-07-01')
        self.assertEqual(str(august.competition_month), '2026-08-01')

    def test_new_year_allows_repeat_and_frozen_results_and_points_remain(self):
        december = self.entry(self.week(2026, 12, 21), state='active')
        result = WeeklyResult.objects.create(week=december.week, entry=december, revision=1,
            placement=1, is_winner=True, league_points=25, weekly_score='80.5')
        award = LeaguePointsAward.objects.create(week=december.week, entry=december, editor=self.member, revision=1, points=25)
        saved = (WeeklyResult.objects.filter(pk=result.pk).values().get(), LeaguePointsAward.objects.filter(pk=award.pk).values().get())
        january = self.entry(self.week(2026, 12, 28))  # Friday January 1.
        self.assertEqual(str(january.competition_month), '2027-01-01')
        self.assertEqual(saved, (WeeklyResult.objects.filter(pk=result.pk).values().get(), LeaguePointsAward.objects.filter(pk=award.pk).values().get()))

    def test_server_overrides_supplied_month_and_keeps_one_editor_per_week(self):
        week = self.week(2026, 10, 5)
        entry = self.entry(week, competition_month=datetime(2000, 1, 1).date())
        self.assertEqual(str(entry.competition_month), '2026-10-01')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(week, video_id='AbCdEfGhI_2')

    def test_backfill_assigns_friday_month_without_changing_history(self):
        entry = self.entry(self.week(2026, 12, 28), state='withdrawn')
        before = CompetitionEntry.objects.filter(pk=entry.pk).values().get()
        # Exercise the same historical-model-compatible routine used by the
        # migration; all historical metadata except the lookup month is stable.
        CompetitionEntry.objects.filter(pk=entry.pk).update(competition_month='2026-12-01')
        migration = import_module('edithub.migrations.0028_monthly_entry_identity')
        migration.assign_competition_month(apps, connection.schema_editor(atomic=False))
        self.assertEqual(CompetitionEntry.objects.filter(pk=entry.pk).values().get(), before)
