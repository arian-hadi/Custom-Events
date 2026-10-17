"""League acceptance tests using isolated test data, never real pilot calibration.

Run with --settings=prime_project.test_settings. No provider or SMTP is contacted.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from edithub.league import services
from edithub.league.calendar import friday_date, monday_for, next_week_start, week_cutoff
from edithub.league.scoring import CalibrationRequired, DataPending, LeagueError, age_band, default_config, percentile, score, validate_config
from edithub.league_models import (
    CompetitionEntry, CompetitionWeek, EntryBaseline, LeaguePointsAward,
    MetricSnapshot, MonthlyAward, ScoringVersion, SeasonAward, WeeklyResult,
)

UTC = timezone.utc
START = datetime(2026, 7, 27, tzinfo=UTC)


def fixture_config():
    """Simple monotonic test scales; these are not suitable for a live league."""
    config = default_config()
    for supported in config["supported_formats"]:
        for band in config["age_bands"]:
            config["references"][f"{supported}:{band['key']}"] = {
                "prior_rate": "0.05", "prior_views": "1000", "baseline_floor": "10", "improvement_cap": "5",
                "response": [["0", "0"], ["1", "100"]],
                "improvement": [["0", "0"], ["5", "100"]],
                "popularity": [["0", "0"], ["10000", "100"]],
            }
    return config


class LeagueCalendarAndScoringTests(SimpleTestCase):
    def test_utc_next_week_intake_and_friday_period_assignment(self):
        self.assertEqual(week_cutoff(START), datetime(2026, 8, 1, tzinfo=UTC))
        self.assertEqual(friday_date(START).isoformat(), "2026-07-31")
        self.assertEqual(next_week_start(START + timedelta(days=6, hours=23)), START + timedelta(days=7))
        self.assertEqual(next_week_start(START + timedelta(days=7)), START + timedelta(days=14))
        local_monday = datetime(2026, 8, 3, 1, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(monday_for(local_monday), START)  # Still Sunday in UTC.
        self.assertEqual(friday_date(datetime(2025, 12, 29, tzinfo=UTC)).year, 2026)
        with self.assertRaises(ValueError):
            week_cutoff(START + timedelta(hours=1))
        with self.assertRaises(ValueError):
            monday_for(datetime(2026, 7, 27))

    def test_age_bands_cover_exact_boundaries_and_old_edits(self):
        config = default_config()
        for days, expected in [(0, "under_7"), (6.999, "under_7"), (7, "7_29"), (30, "30_89"), (90, "90_plus"), (4000, "90_plus")]:
            self.assertEqual(age_band(config, days * 86400), expected)
        with self.assertRaises(LeagueError):
            age_band(config, -1)

    def test_uncalibrated_references_fail_closed(self):
        with self.assertRaises(CalibrationRequired):
            validate_config(default_config())
        config = fixture_config()
        del config["references"]["youtube:short:90_plus"]
        with self.assertRaises(CalibrationRequired):
            validate_config(config)

    def test_malformed_admin_json_reports_calibration_errors(self):
        malformed = [None, [], "not an object", 123]
        for key, value in [("weights", []), ("weights", None), ("neutral_improvement", []),
                           ("placement_points", {}), ("placement_points", [True]), ("age_bands", {}),
                           ("age_bands", [None]), ("age_bands", [{"key": [], "min_days": 0}]),
                           ("supported_formats", [None]), ("supported_formats", ["youtube:short", "youtube:short"]),
                           ("references", []), ("repeat_policy", "weekly_repeats")]:
            config = fixture_config()
            config[key] = value
            malformed.append(config)
        for value in [None, [], "not an object"]:
            config = fixture_config()
            config["references"]["youtube:short:under_7"] = value
            malformed.append(config)
        for key, value in [("prior_rate", None), ("prior_views", "NaN"), ("response", None),
                           ("response", {}), ("response", [[0], [1, 100]]), ("response", [None, None]),
                           ("response", [[{}, 0], [1, 100]])]:
            config = fixture_config()
            config["references"]["youtube:short:under_7"][key] = value
            malformed.append(config)
        missing = fixture_config()
        del missing["neutral_improvement"]
        malformed.append(missing)
        for config in malformed:
            with self.subTest(config=config), self.assertRaises(CalibrationRequired):
                validate_config(config)

    def test_lifetime_likes_are_counted_and_missing_history_is_neutral(self):
        config = fixture_config()
        result = score(config, "youtube:short:90_plus", 8200, 100000)
        self.assertEqual(result["likes"], "8200")
        self.assertEqual(Decimal(result["popularity_score"]), Decimal(82))
        self.assertEqual(Decimal(result["improvement_score"]), Decimal(50))
        self.assertTrue(result["neutral_improvement"])
        growth_only = score(config, "youtube:short:90_plus", 200, 100000)
        self.assertGreater(Decimal(result["weekly_score"]), Decimal(growth_only["weekly_score"]))

    def test_baseline_floor_cap_and_component_clamps(self):
        result = score(fixture_config(), "youtube:short:under_7", 100000, 100000, "0")
        self.assertEqual(Decimal(result["relative_performance"]), Decimal(5))
        self.assertEqual(Decimal(result["improvement_score"]), Decimal(100))
        self.assertEqual(Decimal(result["popularity_score"]), Decimal(100))
        self.assertFalse(result["neutral_improvement"])
        self.assertEqual(percentile(5, [[0, 0], [10, 100]]), 50)
        self.assertEqual(percentile(-5, [[0, 0], [10, 100]]), 0)
        self.assertEqual(percentile(50, [[0, 0], [10, 100]]), 100)

    def test_missing_or_negative_counters_never_become_zero(self):
        for likes, views in [(None, 100), (10, None), (-1, 100), (10, -1)]:
            with self.subTest(likes=likes, views=views), self.assertRaises(DataPending):
                score(fixture_config(), "youtube:short:under_7", likes, views)
        self.assertEqual(score(fixture_config(), "youtube:short:under_7", 0, 0)["likes"], "0")


class LeagueLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.editors = [User.objects.create_user(email=f"league-core-{index}@example.test", username=f"league-core-{index}") for index in range(6)]
        cls.admin = User.objects.create_user(email="league-core-admin@example.test", username="league-core-admin", is_staff=True, is_superuser=True)
        cls.version = ScoringVersion.objects.create(name="isolated-core-fixture", config=fixture_config(), rules_confirmed=True,
            calibrated=True, calibration_notes="Synthetic isolated test fixture; not production pilot evidence.")

    def entry(self, week, index=0):
        identity = f"test-{week.pk}-{index}"
        return CompetitionEntry.objects.create(week=week, editor=self.editors[index], platform="youtube", video_id=identity,
            channel_id=f"channel-{index}", video_format="short", published_at=week.cutoff_at - timedelta(days=30),
            canonical_url=f"https://www.youtube.com/watch?v={identity}", content_key=f"youtube:{identity}")

    def snapshot(self, entry, *, likes=100, views=10000, completed=None, received=None):
        completed = completed or entry.week.cutoff_at - timedelta(minutes=1)
        with patch("edithub.league.services.timezone.now", return_value=received or completed):
            return services.record_snapshot(entry, {"likes": likes, "views": views, "completed_at": completed, "provider": "isolated-fixture"})

    def round(self, start=START, likes=None):
        likes = likes or [500, 400, 300, 200, 100]
        week = services.ensure_week(start, self.version)
        entries = [self.entry(week, index) for index in range(len(likes))]
        week = services.activate_week(week, now=week.start_at)
        for entry, count in zip(entries, likes):
            self.snapshot(entry, likes=count)
        return week, entries

    def finish(self, week):
        return services.finalize_week(week, now=week.cutoff_at)

    def test_live_api_projects_versioned_points_without_awarding_or_inventing_missing_data(self):
        self.version.config['placement_points'][0] = 31
        self.version.save()
        week, entries = self.round(likes=[500, 400])
        moment = week.cutoff_at - timedelta(seconds=30)
        with patch('platform_api.league_views.timezone.now', return_value=moment):
            data = self.client.get('/api/v2/league/standings/', {'period': 'week', 'week': week.pk}).json()
        self.assertEqual([row['projected_points'] for row in data['rows']], [31, 20])
        self.assertTrue(all(row['points'] is None for row in data['rows']))
        self.assertEqual(data['minimum_entries'], 5)
        self.assertFalse(LeaguePointsAward.objects.exists())
        entries[1].snapshots.all().delete()
        with patch('platform_api.league_views.timezone.now', return_value=moment):
            data = self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()
        self.assertIsNone(data['rows'][-1]['projected_points'])
        self.assertIsNone(data['rows'][-1]['rank'])

    def test_all_time_sums_finalized_effective_awards_across_years_once(self):
        first, _ = self.round()
        self.finish(first)
        self.finish(first)
        services.finalize_month(2026, 7, now=first.cutoff_at)
        second, _ = self.round(start=START.replace(year=2027, month=1, day=4))
        self.finish(second)
        live, _ = self.round(start=START.replace(year=2027, month=1, day=11))
        rows = services.aggregate_standings()
        self.assertEqual(rows[0]['points'], 50)
        self.assertEqual(len(rows[0]['entry_ids']), 2)
        self.assertEqual(services.aggregate_standings(2026)[0]['points'], 25)
        data = self.client.get('/api/v2/league/standings/', {'period': 'all_time'}).json()
        self.assertEqual(data['rows'][0]['points'], 50)
        self.assertIn('video_url', data['rows'][0])
        self.assertFalse(data['provisional'])
        services.correct_week(second, reason='Test correction', actor=self.admin,
            disqualified_entry_ids=[second.entries.get(editor=self.editors[0]).pk], now=second.cutoff_at)
        self.assertEqual(next(row for row in services.aggregate_standings() if row['editor_id'] == self.editors[0].pk)['points'], 25)

    def test_activation_freezes_rules_baselines_and_one_persistent_draw(self):
        week, entries = self.round()
        repeated = services.activate_week(week, now=week.start_at + timedelta(hours=2))
        self.assertEqual(repeated.tie_seed, week.tie_seed)
        self.assertEqual(EntryBaseline.objects.filter(entry__week=week).count(), 5)
        entries[0].refresh_from_db()
        self.assertEqual(entries[0].age_band, "30_89")
        self.assertIsNone(entries[0].baseline.median_likes)
        entries[0].video_id = "changed"
        with self.assertRaises(ValidationError):
            entries[0].save()
        self.version.refresh_from_db()
        self.version.config = deepcopy(self.version.config)
        self.version.config["weights"] = {"response": "0.6", "improvement": "0.2", "popularity": "0.2"}
        with self.assertRaises(ValidationError):
            self.version.save()

    def test_baseline_uses_distinct_age_matched_observations_available_at_activation(self):
        week = services.ensure_week(START, self.version)
        entry = self.entry(week)
        accepted = []
        for index in range(5):
            completed = START - timedelta(days=index + 1)
            values = dict(editor=entry.editor, platform="youtube", video_id=f"comparison-{index}", channel_id=entry.channel_id,
                video_format="short", published_at=completed - timedelta(days=30), provider="isolated-fixture", views=10000, status="success")
            accepted.append(MetricSnapshot.objects.create(**values, likes=(index + 1) * 100, requested_at=completed,
                completed_at=completed, received_at=completed))
            # Same video, less comparable age: must not add a second sample.
            MetricSnapshot.objects.create(**values, likes=999999, requested_at=completed + timedelta(hours=1),
                completed_at=completed + timedelta(hours=1), received_at=completed + timedelta(hours=1))
        # A late response claiming an earlier observation was not known at activation.
        MetricSnapshot.objects.create(editor=entry.editor, platform="youtube", video_id="late-history", channel_id=entry.channel_id,
            video_format="short", published_at=START - timedelta(days=31), provider="isolated-fixture", likes=999999, views=10000,
            status="success", requested_at=START - timedelta(days=1), completed_at=START - timedelta(days=1), received_at=START + timedelta(hours=1))
        services.activate_week(week, now=START + timedelta(hours=2))
        self.assertEqual(set(entry.baseline.sample_ids), {row.pk for row in accepted})
        self.assertEqual(entry.baseline.sample_count, 5)
        self.assertEqual(Decimal(entry.baseline.median_likes), Decimal(300))

    def test_finalization_uses_latest_eligible_counter_even_when_it_decreased(self):
        week, entries = self.round()
        newest = self.snapshot(entries[0], likes=50, completed=week.cutoff_at - timedelta(seconds=30))
        self.assertTrue(newest.provenance["counter_decrease"])
        self.finish(week)
        result = WeeklyResult.objects.get(entry=entries[0], revision=1)
        self.assertEqual(result.snapshot_id, newest.pk)
        self.assertEqual(result.details["likes"], "50")
        self.assertEqual(result.placement, 5)

    def test_snapshot_cannot_silently_change_frozen_provider_identity(self):
        week = services.ensure_week(START, self.version)
        entry = self.entry(week)
        completed = START - timedelta(hours=1)
        payload = {"likes": 100, "views": 10000, "completed_at": completed, "provider": "isolated-fixture"}
        for field, value in [("platform", "tiktok"), ("video_id", "someone-elses-edit"), ("channel_id", "other-channel"),
                             ("video_format", "long"), ("published_at", entry.published_at + timedelta(days=1))]:
            with self.subTest(field=field), patch("edithub.league.services.timezone.now", return_value=completed), self.assertRaises(LeagueError):
                services.record_snapshot(entry, {**payload, field: value})
        self.assertFalse(entry.snapshots.exists())
        identity = {field: getattr(entry, field) for field in ("platform", "video_id", "channel_id", "video_format", "published_at")}
        with patch("edithub.league.services.timezone.now", return_value=completed):
            services.record_snapshot(entry, {**payload, **identity})
        self.assertEqual(entry.snapshots.count(), 1)

    def test_cutoff_is_exclusive_and_missing_closing_data_blocks_all_awards(self):
        week = services.ensure_week(START, self.version)
        entry = self.entry(week)
        week = services.activate_week(week, now=START)
        self.snapshot(entry, completed=week.cutoff_at - timedelta(minutes=15, microseconds=1))
        self.snapshot(entry, likes=999999, completed=week.cutoff_at)
        self.snapshot(entry, likes=9999999, completed=week.cutoff_at + timedelta(seconds=1))
        with self.assertRaises(DataPending):
            services.finalize_week(week, now=week.cutoff_at + timedelta(days=1))
        self.assertFalse(WeeklyResult.objects.exists())
        self.assertFalse(LeaguePointsAward.objects.exists())
        week.refresh_from_db()
        self.assertEqual(week.current_revision, 0)
        self.snapshot(entry, completed=week.cutoff_at - timedelta(minutes=15))
        self.finish(week)  # Exactly the maximum permitted age is eligible.
        self.assertEqual(WeeklyResult.objects.get().details["likes"], "100")

    def test_unactivated_round_cannot_reconstruct_history_after_cutoff(self):
        week = services.ensure_week(START, self.version)
        with self.assertRaises(DataPending):
            self.finish(week)
        with self.assertRaises(LeagueError):
            services.activate_week(week, now=week.cutoff_at)

    def test_fewer_than_five_finishers_is_exhibition_without_winner_or_points(self):
        week, _ = self.round(likes=[500, 400, 300, 200])
        revision = self.finish(week)
        self.assertEqual(revision.state, "exhibition")
        self.assertEqual(week.results.count(), 4)
        self.assertFalse(week.results.filter(is_winner=True).exists())
        self.assertFalse(week.points_awards.exclude(points=0).exists())
        self.assertEqual(services.aggregate_standings(2026), [])

    def test_final_results_draw_and_points_do_not_change_on_retry_or_weekend_fetch(self):
        week, entries = self.round(likes=[100] * 5)
        initial = self.finish(week)
        before = list(week.results.values("entry_id", "placement", "weekly_score", "league_points", "details"))
        self.snapshot(entries[0], likes=900000, completed=week.cutoff_at + timedelta(hours=3))
        repeated = services.finalize_week(week, now=week.cutoff_at + timedelta(days=1))
        self.assertEqual(repeated.pk, initial.pk)
        self.assertEqual(list(week.results.values("entry_id", "placement", "weekly_score", "league_points", "details")), before)
        self.assertEqual(week.points_awards.filter(effective=True).count(), 5)
        self.assertEqual(week.results.filter(is_winner=True).count(), 1)
        self.assertEqual([row["entry_id"] for row in services.provisional_standings(week)], [row["entry_id"] for row in before])

    def test_weekly_ranking_preserves_more_than_twenty_eight_decimal_digits(self):
        week, entries = self.round()
        original = services.score
        def precise_score(config, reference_key, likes, views, baseline):
            row = original(config, reference_key, likes, views, baseline)
            row.update(weekly_score="50.000000000000000000000000000000000000000000001" if likes == 400 else "50.000000000000000000000000000000000000000000000",
                       response_score="50", improvement_score="50")
            return row
        with patch("edithub.league.services.score", side_effect=precise_score), patch("edithub.league.services._draw", side_effect=lambda seed, identity: str(identity).zfill(10)):
            self.finish(week)
        self.assertEqual(week.results.get(is_winner=True).entry_id, entries[1].pk)

    def test_correction_preserves_previous_revision_and_rebuilds_period_awards(self):
        week, entries = self.round(likes=[600, 500, 400, 300, 200, 100])
        self.finish(week)
        august = datetime(2026, 8, 1, tzinfo=UTC)
        month = services.finalize_month(2026, 7, now=august)
        season = SeasonAward.objects.create(year=2026, revision=1, editor=self.editors[0], points=25, details={"archived": True})
        revision = services.correct_week(week, reason="Test audited disqualification", actor=self.admin,
            disqualified_entry_ids=[entries[0].pk], now=datetime(2027, 1, 2, tzinfo=UTC))
        self.assertEqual(revision.number, 2)
        self.assertEqual(revision.actor_id, self.admin.pk)
        self.assertTrue(week.results.get(entry=entries[0], revision=1).is_winner)
        self.assertTrue(week.results.get(entry=entries[1], revision=2).is_winner)
        self.assertFalse(week.points_awards.filter(revision=1, effective=True).exists())
        self.assertEqual(week.points_awards.filter(effective=True).count(), 6)
        month.refresh_from_db()
        season.refresh_from_db()
        self.assertFalse(month.effective)
        self.assertTrue(season.effective)  # Retired annual archive stays unchanged.
        self.assertEqual(MonthlyAward.objects.get(effective=True).editor_id, entries[1].editor_id)
        self.assertEqual(SeasonAward.objects.get(effective=True).editor_id, entries[0].editor_id)
        self.assertEqual(MonthlyAward.objects.get(effective=True).details["tie_seed"], month.details["tie_seed"])

    def test_correction_requires_permission_reason_and_real_closing_snapshot(self):
        week, entries = self.round()
        self.finish(week)
        for actor, reason in [(self.editors[0], "Reason"), (self.admin, " ")]:
            with self.assertRaises(LeagueError):
                services.correct_week(week, reason=reason, actor=actor, now=week.cutoff_at)
        late = self.snapshot(entries[0], completed=week.cutoff_at + timedelta(seconds=1))
        with self.assertRaises(DataPending):
            services.correct_week(week, reason="Late data cannot reconstruct a closing total", actor=self.admin,
                snapshot_overrides={entries[0].pk: late.pk}, now=week.cutoff_at + timedelta(days=1))
        self.assertEqual(week.revisions.count(), 1)

    def test_audited_reinstatement_is_preserved_by_later_corrections(self):
        week, entries = self.round(likes=[600, 500, 400, 300, 200, 100])
        entries[0].refresh_from_db()
        entries[0].state = "disqualified"
        entries[0].moderation_reason = "Initial moderation decision"
        entries[0].save(update_fields=["state", "moderation_reason"])
        self.finish(week)
        self.assertTrue(week.results.get(entry=entries[0], revision=1).details["disqualified"])
        services.correct_week(week, actor=self.admin, reason="Successful appeal with valid closing data",
            disqualified_entry_ids=[], now=week.cutoff_at + timedelta(hours=1))
        self.assertTrue(week.results.get(entry=entries[0], revision=2).is_winner)
        services.correct_week(week, actor=self.admin, reason="Confirm closing data", now=week.cutoff_at + timedelta(hours=2))
        self.assertTrue(week.results.get(entry=entries[0], revision=3).is_winner)
        self.assertTrue(week.results.get(entry=entries[0], revision=1).details["disqualified"])

    def test_period_representative_uses_full_score_precision(self):
        low_week, low_entries = self.round(START - timedelta(days=7))
        high_week, high_entries = self.round(START)
        low = "50.000000000000000000000000000000000000000000001"
        high = "50.000000000000000000000000000000000000000000002"
        original = services.score
        def finalize_precise(week, value):
            def precise_score(config, reference_key, likes, views, baseline):
                row = original(config, reference_key, likes, views, baseline)
                if likes == 500:
                    row.update(weekly_score=value, response_score="50")
                return row
            with patch("edithub.league.services.score", side_effect=precise_score):
                self.finish(week)
        finalize_precise(low_week, low)
        finalize_precise(high_week, high)
        award = services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        self.assertEqual(award.editor_id, self.editors[0].pk)
        self.assertEqual(award.entry_id, high_entries[0].pk)

    def test_cancellation_removes_effective_points_without_erasing_results(self):
        week, _ = self.round()
        self.finish(week)
        services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        canceled = services.cancel_week(week, actor=self.admin, reason="Unreliable provider data", now=datetime(2026, 8, 2, tzinfo=UTC))
        repeated = services.cancel_week(week, actor=self.admin, reason="Retry", now=datetime(2026, 8, 2, tzinfo=UTC))
        self.assertEqual(repeated.pk, canceled.pk)
        self.assertTrue(week.results.filter(revision=1, is_winner=True).exists())
        self.assertFalse(week.points_awards.filter(effective=True).exclude(points=0).exists())
        self.assertEqual(services.aggregate_standings(2026), [])
        self.assertIsNone(MonthlyAward.objects.get(effective=True).editor_id)

    def test_monthly_winner_accumulates_points_and_can_have_no_weekly_win(self):
        final_week = None
        for offset, likes in [(-2, [400, 500, 300, 200, 100]), (-1, [500, 400, 600, 300, 100]), (0, [600, 500, 400, 700, 100])]:
            final_week, entries = self.round(START + timedelta(weeks=offset), likes=likes)
            self.finish(final_week)
        winner = services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        self.assertEqual(winner.editor_id, self.editors[0].pk)
        self.assertEqual(winner.points, 60)
        self.assertEqual(winner.entry_id, entries[0].pk)
        self.assertFalse(WeeklyResult.objects.filter(entry__editor=self.editors[0], is_winner=True).exists())
        self.assertEqual(services.finalize_month(2026, 7, now=datetime(2026, 8, 2, tzinfo=UTC)).pk, winner.pk)
        self.assertEqual(services.aggregate_standings(2026, 8), [])  # Saturday publication is in August.
        with self.assertRaises(LeagueError):
            services.finalize_season(2026, now=datetime(2027, 1, 1, tzinfo=UTC))
        self.assertFalse(SeasonAward.objects.exists())
        self.assertEqual(services.aggregate_standings(2027), [])

    def test_unresolved_round_blocks_period_awards_and_finalized_period_cannot_gain_rounds(self):
        week = services.ensure_week(START, self.version)
        with self.assertRaises(DataPending):
            services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        with self.assertRaises(LeagueError):
            services.finalize_season(2026, now=datetime(2027, 1, 1, tzinfo=UTC))
        services.cancel_week(week, reason="No valid collection", actor=self.admin, now=week.cutoff_at)
        services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        with self.assertRaises(LeagueError):
            services.ensure_week(START - timedelta(days=7), self.version)
        self.assertEqual(CompetitionWeek.objects.count(), 1)
        services.ensure_week(START + timedelta(days=7), self.version)
        self.assertEqual(CompetitionWeek.objects.count(), 2)

    def test_aggregate_ranking_preserves_full_score_precision(self):
        # Equal league points and placement profiles; total score must decide
        # before an arbitrary ID or tie draw, even far beyond display precision.
        low = Decimal("50.000000000000000000000000000000000000000000001")
        high = Decimal("50.000000000000000000000000000000000000000000002")
        from collections import Counter
        rows = {1: {"editor_id": 1, "points": 20, "placements": Counter({2: 1}), "weekly_score_total": low, "entry_ids": [1]},
                2: {"editor_id": 2, "points": 20, "placements": Counter({2: 1}), "weekly_score_total": high, "entry_ids": [2]}}
        with patch("edithub.league.services._aggregate_results", return_value=(rows, [])):
            standings = services.aggregate_standings(2026)
        self.assertEqual([row["editor_id"] for row in standings], [2, 1])
        self.assertEqual([row["rank"] for row in standings], [1, 2])

    def test_monthly_72_points_reset_and_late_join_without_catchup(self):
        for offset, likes in enumerate([
            [500, 600, 400, 300, 200, 100], [200, 600, 500, 400, 300, 100],
            [600, 500, 400, 300, 200, 100], [400, 600, 500, 300, 200, 100],
        ]):
            week, _ = self.round(START - timedelta(weeks=3-offset), likes=likes)
            self.finish(week)
        july = services.monthly_standings(2026, 7)
        self.assertEqual(next(row for row in july if row['editor_id'] == self.editors[0].pk)['points'], 72)
        self.assertEqual(services.monthly_standings(2026, 8), [])
        newcomer = get_user_model().objects.create_user(username='late-editor', email='late@example.test', is_verified=True)
        self.client.force_login(newcomer)
        with patch('platform_api.member_views.timezone.now', return_value=START):
            data = self.client.get('/api/v2/member/dashboard/').json()
        self.assertEqual(data['league']['month']['points'], 0)
        self.assertIsNone(data['league']['month']['rank'])
        self.assertNotIn('season_standing', data['league'])
        self.assertEqual(services.monthly_standings(2026, 7), july)

    def test_year_boundary_and_annual_worker_retirement_preserve_archive(self):
        from django.core.management import call_command
        from io import StringIO
        previous, _ = self.round(datetime(2026, 12, 21, tzinfo=UTC))
        january, _ = self.round(datetime(2026, 12, 28, tzinfo=UTC))
        self.finish(previous)
        self.finish(january)
        self.assertEqual(previous.scoring_date.month, 12)
        self.assertEqual((january.scoring_date.year, january.scoring_date.month), (2027, 1))
        self.assertEqual(services.monthly_standings(2026, 12)[0]['points'], 25)
        self.assertEqual(services.monthly_standings(2027, 1)[0]['points'], 25)
        archive = SeasonAward.objects.create(year=2025, revision=1, points=123, details={'legacy': True})
        with patch('edithub.management.commands.league_tick.timezone.now', return_value=datetime(2027, 2, 1, tzinfo=UTC)):
            call_command('league_tick', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(SeasonAward.objects.count(), 1)
        archive.refresh_from_db()
        self.assertEqual(archive.points, 123)
        self.assertEqual(self.client.get('/api/v2/league/standings/?period=season').status_code, 400)

    def test_monthly_tie_is_persisted_and_public_standings_match_single_winner(self):
        first, _ = self.round(START - timedelta(days=7), likes=[600, 500, 400, 300, 200, 100])
        second, _ = self.round(START, likes=[500, 600, 400, 300, 200, 100])
        self.finish(first)
        self.finish(second)
        before = list(LeaguePointsAward.objects.values())
        month = services.finalize_month(2026, 7, now=datetime(2026, 8, 1, tzinfo=UTC))
        repeated = services.finalize_month(2026, 7, now=datetime(2026, 8, 2, tzinfo=UTC))
        self.assertEqual(month.pk, repeated.pk)
        self.assertEqual(month.points, 45)
        rows = services.monthly_standings(2026, 7)
        self.assertEqual(rows[0]['editor_id'], month.editor_id)
        self.assertEqual(sum(row['rank'] == 1 for row in rows), 1)
        self.assertEqual(list(LeaguePointsAward.objects.values()), before)  # No monthly bonus points.
        data = self.client.get('/api/v2/league/standings/?period=month&year=2026&month=7').json()
        self.assertEqual(data['state'], 'finalized')
        self.assertFalse(data['provisional'])
        self.assertEqual(data['rows'][0]['editor_id'], month.editor_id)
