"""Staff league acceptance tests using an isolated database and synthetic scales.

No live provider, production calibration or outbound email is used here.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from edithub.league import services
from edithub.league_admin import RoundOperationForm
from edithub.league_models import (
    CompetitionEntry, CompetitionWeek, EntryBaseline, LeaguePointsAward,
    LeagueSeason, MetricSnapshot, MonthlyAward, ScoringVersion, SeasonAward,
    WeeklyResult, WeeklyRevision,
)
from edithub.test_league_core import START, fixture_config


@override_settings(LEAGUE_ENABLED=False)
class LeagueAdministrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(email="league-admin@example.test", username="league-admin",
                                            is_staff=True, is_superuser=True)
        cls.operator = User.objects.create_user(email="league-operator@example.test", username="league-operator", is_staff=True)
        cls.operator.user_permissions.add(Permission.objects.get(codename="change_competitionweek"))
        cls.viewer = User.objects.create_user(email="league-viewer@example.test", username="league-viewer", is_staff=True)
        cls.viewer.user_permissions.add(Permission.objects.get(codename="view_competitionweek"))
        cls.staff = User.objects.create_user(email="league-staff@example.test", username="league-staff", is_staff=True)
        cls.member = User.objects.create_user(email="league-member@example.test", username="league-member")
        cls.editors = [User.objects.create_user(email=f"admin-editor-{n}@example.test", username=f"admin-editor-{n}") for n in range(6)]
        cls.version = ScoringVersion.objects.create(name="isolated-admin-fixture", config=fixture_config(),
            rules_confirmed=True, calibrated=True, calibration_notes="Synthetic isolated acceptance test only; not real pilot evidence.")

    def setUp(self):
        self.client.force_login(self.owner)

    def schedule_url(self):
        return reverse("admin:edithub_competitionweek_schedule")

    def operation_url(self, week):
        return reverse("admin:edithub_competitionweek_operations", args=[week.pk])

    def schedule_data(self, **kwargs):
        return {"scoring_version": self.version.pk, "start_date": START.date().isoformat(), "count": 2, **kwargs}

    def round(self, *, activate=True, snapshots=True):
        week = services.ensure_week(START, self.version)
        entries = [CompetitionEntry.objects.create(week=week, editor=editor, platform="youtube", video_id=f"admin-fixture-{n}",
            channel_id=f"channel-{n}", video_format="short", published_at=week.cutoff_at - timedelta(days=30),
            canonical_url=f"https://www.youtube.com/watch?v=admin-fixture-{n}", title=f"Isolated test edit {n}")
            for n, editor in enumerate(self.editors)]
        if activate:
            week = services.activate_week(week, now=START)
        if snapshots:
            completed = week.cutoff_at - timedelta(minutes=1)
            with patch("edithub.league.services.timezone.now", return_value=completed):
                for n, entry in enumerate(entries):
                    services.record_snapshot(entry, {"likes": 600 - 100 * n, "views": 10000,
                        "completed_at": completed, "provider": "isolated-fixture"})
        return week, entries

    def post_operation(self, week, operation, *, now=None, **kwargs):
        with patch("edithub.league.services.timezone.now", return_value=now or week.cutoff_at):
            return self.client.post(self.operation_url(week), {"operation": operation, **kwargs})

    def test_permission_boundary_for_round_views_and_mutations(self):
        week = services.ensure_week(START, self.version)
        for user, get_status, post_status in [(self.viewer, 200, 403), (self.staff, 403, 403), (self.operator, 200, 302)]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                response = self.client.get(self.operation_url(week))
                self.assertEqual(response.status_code, get_status)
                if user == self.viewer:
                    self.assertNotContains(response, "Run selected operation")
                response = self.post_operation(week, "cancel", reason="Acceptance permission test")
                self.assertEqual(response.status_code, post_status)
        self.assertEqual(week.revisions.count(), 1)
        self.assertEqual(week.revisions.get().actor_id, self.operator.pk)
        for user in [self.member, None]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.assertEqual(self.client.get(self.operation_url(week)).status_code, 302)
            self.assertEqual(self.client.post(self.schedule_url(), self.schedule_data()).status_code, 302)

    def test_schedule_requires_round_change_permission(self):
        for user in [self.viewer, self.staff]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.schedule_url()).status_code, 403)
            self.assertEqual(self.client.post(self.schedule_url(), self.schedule_data()).status_code, 403)
        self.assertFalse(CompetitionWeek.objects.exists())
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(self.schedule_url(), self.schedule_data()).status_code, 302)
        self.assertEqual(CompetitionWeek.objects.count(), 2)

    def test_get_requests_never_schedule_or_operate(self):
        response = self.client.get(self.schedule_url(), self.schedule_data())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompetitionWeek.objects.exists())
        week = services.ensure_week(START, self.version)
        response = self.client.get(self.operation_url(week), {"operation": "cancel", "reason": "Not a POST"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(week.revisions.exists())
        self.assertContains(response, "disabled by LEAGUE_ENABLED")

    def test_custom_admin_endpoints_enforce_csrf(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        week = services.ensure_week(START, self.version)
        self.assertEqual(secure.post(self.schedule_url(), self.schedule_data()).status_code, 403)
        self.assertEqual(secure.post(self.operation_url(week), {"operation": "cancel", "reason": "Missing CSRF"}).status_code, 403)
        self.assertFalse(week.revisions.exists())
        secure.get(self.operation_url(week))
        response = secure.post(self.operation_url(week), {"operation": "cancel", "reason": "Valid CSRF",
            "csrfmiddlewaretoken": secure.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(week.revisions.get().reason, "Valid CSRF")

    def test_scheduling_is_idempotent_utc_and_validates_monday(self):
        invalid = self.client.post(self.schedule_url(), self.schedule_data(start_date=(START + timedelta(days=1)).date()))
        self.assertContains(invalid, "Choose a Monday")
        self.assertFalse(CompetitionWeek.objects.exists())
        for _ in range(2):
            self.assertEqual(self.client.post(self.schedule_url(), self.schedule_data()).status_code, 302)
        weeks = list(CompetitionWeek.objects.order_by("start_at"))
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0].start_at, START)
        self.assertEqual(weeks[0].cutoff_at, START + timedelta(days=5))
        self.assertEqual(weeks[0].scoring_date, (START + timedelta(days=4)).date())
        self.assertEqual(weeks[0].state, "scheduled")
        self.version.refresh_from_db()
        self.assertIsNone(self.version.frozen_at)

    def test_multiweek_schedule_conflict_rolls_back_whole_batch_and_log(self):
        alternate = ScoringVersion.objects.create(name="other-draft")
        existing = services.ensure_week(START + timedelta(weeks=1), alternate)
        response = self.client.post(self.schedule_url(), self.schedule_data())
        self.assertContains(response, "already has a different scoring version")
        self.assertEqual(list(CompetitionWeek.objects.values_list("pk", flat=True)), [existing.pk])
        self.assertFalse(LogEntry.objects.exists())

    def test_draft_versions_can_be_scheduled_but_not_activated(self):
        draft = ScoringVersion.objects.create(name="uncalibrated-draft")
        response = self.client.post(self.schedule_url(), self.schedule_data(scoring_version=draft.pk, count=1))
        self.assertEqual(response.status_code, 302)
        week = CompetitionWeek.objects.get()
        response = self.post_operation(week, "activate", now=START)
        self.assertContains(response, "documented pilot calibration")
        week.refresh_from_db()
        self.assertIsNone(week.activated_at)
        draft.refresh_from_db()
        self.assertIsNone(draft.frozen_at)

    def test_activate_finalizes_only_with_valid_closing_metrics_and_logs_operator(self):
        week, entries = self.round(activate=False, snapshots=False)
        response = self.post_operation(week, "activate", now=START)
        self.assertEqual(response.status_code, 302)
        week.refresh_from_db()
        self.assertEqual(week.state, "live")
        self.assertEqual(EntryBaseline.objects.count(), len(entries))
        response = self.post_operation(week, "finalize")
        self.assertContains(response, "Closing metrics are missing")
        self.assertFalse(WeeklyRevision.objects.exists())
        completed = week.cutoff_at - timedelta(minutes=1)
        with patch("edithub.league.services.timezone.now", return_value=completed):
            for n, entry in enumerate(entries):
                services.record_snapshot(entry, {"likes": 600 - n * 100, "views": 10000, "completed_at": completed, "provider": "isolated-fixture"})
        self.assertEqual(self.post_operation(week, "finalize").status_code, 302)
        week.refresh_from_db()
        self.assertEqual(week.state, "finalized")
        self.assertEqual(week.current_revision, 1)
        self.assertEqual(week.results.filter(is_winner=True).count(), 1)
        self.assertEqual(LogEntry.objects.filter(user=self.owner, change_message__contains="League operation: finalize").count(), 1)
        self.assertEqual(self.post_operation(week, "finalize").status_code, 302)
        self.assertEqual(week.revisions.count(), 1)

    def test_correction_requires_reason_and_preserves_prior_results(self):
        week, entries = self.round()
        services.finalize_week(week, now=week.cutoff_at)
        original = list(week.results.values("entry_id", "placement", "league_points", "snapshot_id"))
        response = self.post_operation(week, "correct", disqualified_entry_ids=json.dumps([entries[0].pk]))
        self.assertContains(response, "An audit reason is required")
        self.assertEqual(week.revisions.count(), 1)
        response = self.post_operation(week, "correct", reason="Duplicate source confirmed by staff",
                                       disqualified_entry_ids=json.dumps([entries[0].pk]))
        self.assertEqual(response.status_code, 302)
        revision = week.revisions.get(number=2)
        self.assertEqual(revision.actor_id, self.owner.pk)
        self.assertEqual(revision.reason, "Duplicate source confirmed by staff")
        self.assertEqual(list(week.results.filter(revision=1).values("entry_id", "placement", "league_points", "snapshot_id")), original)
        self.assertEqual(week.results.get(revision=2, is_winner=True).entry_id, entries[1].pk)
        self.assertFalse(week.points_awards.filter(revision=1, effective=True).exists())
        self.assertEqual(week.points_awards.filter(revision=2, effective=True).count(), 6)
        self.assertContains(self.client.get(self.operation_url(week)), "Duplicate source confirmed by staff")

    def test_cancel_requires_reason_creates_audited_zero_point_revision(self):
        week, _ = self.round()
        self.assertContains(self.post_operation(week, "cancel", reason="  "), "An audit reason is required")
        self.assertFalse(week.revisions.exists())
        self.assertEqual(self.post_operation(week, "cancel", reason="Provider outage, no reliable closing observations").status_code, 302)
        week.refresh_from_db()
        self.assertEqual(week.state, "canceled")
        self.assertEqual(week.revisions.get().actor_id, self.owner.pk)
        self.assertFalse(week.points_awards.exclude(points=0).exists())
        self.assertFalse(week.results.filter(is_winner=True).exists())
        self.assertEqual(self.post_operation(week, "cancel", reason="Repeat request").status_code, 302)
        self.assertEqual(week.revisions.count(), 1)

    def test_correction_rejects_other_entry_snapshots_and_post_cutoff_metrics(self):
        week, entries = self.round()
        services.finalize_week(week, now=week.cutoff_at)
        wrong = entries[1].snapshots.get()
        response = self.post_operation(week, "correct", reason="Invalid cross-entry replacement",
                                       snapshot_overrides=json.dumps({str(entries[0].pk): wrong.pk}))
        self.assertContains(response, "snapshot belonging to its entry")
        completed = week.cutoff_at + timedelta(seconds=1)
        with patch("edithub.league.services.timezone.now", return_value=completed):
            late = services.record_snapshot(entries[0], {"likes": 9999, "views": 20000, "completed_at": completed, "provider": "isolated-fixture"})
        response = self.post_operation(week, "correct", now=completed + timedelta(seconds=1), reason="Late data is not historical data",
                                       snapshot_overrides=json.dumps({str(entries[0].pk): late.pk}))
        self.assertContains(response, "cannot invent missing closing metrics")
        self.assertEqual(week.revisions.count(), 1)

    def test_correction_accepts_valid_snapshot_override_and_can_clear_disqualification(self):
        week, entries = self.round()
        services.finalize_week(week, now=week.cutoff_at)
        original_snapshot = entries[0].snapshots.get()
        services.correct_week(week, actor=self.owner, reason="Initial review", disqualified_entry_ids=[entries[0].pk], now=week.cutoff_at)
        response = self.post_operation(week, "correct", reason="Review reinstated original entry",
            snapshot_overrides=json.dumps({str(entries[0].pk): original_snapshot.pk}), disqualified_entry_ids="[]")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(week.results.get(revision=3, is_winner=True).entry_id, entries[0].pk)
        self.assertEqual(week.results.get(revision=3, entry=entries[0]).snapshot_id, original_snapshot.pk)

    def test_operation_payloads_reject_invalid_json_shapes_and_foreign_entries(self):
        week, entries = self.round()
        invalid = [
            {"snapshot_overrides": "[]"}, {"snapshot_overrides": '{"1": true}'},
            {"snapshot_overrides": '{"0": 1}'}, {"snapshot_overrides": '{"+1": 1}'},
            {"snapshot_overrides": '{"999999": 1}'},
            {"disqualified_entry_ids": "{}"}, {"disqualified_entry_ids": "[true]"},
            {"disqualified_entry_ids": "[999999]"},
            {"disqualified_entry_ids": json.dumps([entries[0].pk, entries[0].pk])},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                form = RoundOperationForm({"operation": "correct", "reason": "Malformed input", **payload}, week=week)
                self.assertFalse(form.is_valid())
        for operation in ["activate", "finalize", "cancel"]:
            form = RoundOperationForm({"operation": operation, "reason": "Test", "disqualified_entry_ids": "[]"}, week=week)
            self.assertFalse(form.is_valid())

    def test_all_audit_models_deny_add_edit_delete_and_bulk_actions_even_to_superuser(self):
        week, _ = self.round()
        services.finalize_week(week, now=week.cutoff_at)
        services.finalize_month(2026, 7, now=week.cutoff_at)
        SeasonAward.objects.create(year=2026, revision=1, points=0, details={"archived": True})
        request = RequestFactory().get("/admin/")
        request.user = self.owner
        models = [LeagueSeason, CompetitionWeek, CompetitionEntry, MetricSnapshot, EntryBaseline,
                  WeeklyRevision, WeeklyResult, LeaguePointsAward, MonthlyAward, SeasonAward]
        for model in models:
            obj = model.objects.first()
            model_admin = admin.site._registry[model]
            name = model._meta.model_name
            with self.subTest(model=name):
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request, obj))
                self.assertFalse(model_admin.has_delete_permission(request, obj))
                self.assertEqual(model_admin.get_actions(request), {})
                self.assertEqual(set(model_admin.get_readonly_fields(request, obj)), {field.name for field in model._meta.fields})
                change_url = reverse(f"admin:edithub_{name}_change", args=[obj.pk])
                self.assertEqual(self.client.get(change_url).status_code, 200)
                self.assertEqual(self.client.post(change_url, {"_save": "Save", "state": "live"}).status_code, 403)
                self.assertEqual(self.client.post(reverse(f"admin:edithub_{name}_add"), {}).status_code, 403)
                self.assertEqual(self.client.post(reverse(f"admin:edithub_{name}_delete", args=[obj.pk]), {"post": "yes"}).status_code, 403)

    def test_frozen_scoring_version_is_readonly_but_new_draft_is_editable(self):
        week, _ = self.round()
        self.version.refresh_from_db()
        change_url = reverse("admin:edithub_scoringversion_change", args=[self.version.pk])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(self.client.post(change_url, {"name": "changed", "_save": "Save"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:edithub_scoringversion_delete", args=[self.version.pk]), {"post": "yes"}).status_code, 403)
        response = self.client.post(reverse("admin:edithub_scoringversion_add"),
            {"name": "new-draft", "config": json.dumps(fixture_config()), "calibration_notes": "Draft only", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ScoringVersion.objects.get(name="new-draft").calibrated)

    def test_malformed_calibrated_config_shows_validation_error_not_server_error(self):
        for config in [[], {"weights": []}, {"age_bands": [None]}, {"references": {"unknown": []}}, {"weights": {"response": "NaN"}}]:
            with self.subTest(config=config):
                response = self.client.post(reverse("admin:edithub_scoringversion_add"),
                    {"name": "malformed", "config": json.dumps(config), "calibrated": "on", "rules_confirmed": "on",
                     "calibration_notes": "Not usable", "_save": "Save"})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertFalse(ScoringVersion.objects.filter(name="malformed").exists())

    def test_unknown_round_operation_page_is_404(self):
        response = self.client.get(reverse("admin:edithub_competitionweek_operations", args=[999999]))
        self.assertEqual(response.status_code, 404)
