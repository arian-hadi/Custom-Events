from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from edithub.league import services
from edithub.league.calendar import monday_for, next_week_start
from edithub.league.scoring import default_config
from edithub.league_models import CompetitionEntry, CompetitionWeek, LeaguePointsAward, LeagueSeason, ScoringVersion, WeeklyResult
from edithub.models import EditorApplication, EditorTitle, EditSubmission
from events.models import Event, EventApplication
from notifications.models import Notification
from shop.models import PaymentOrder, Product


NOW = datetime(2026, 10, 2, 12, tzinfo=dt_timezone.utc)
URL = "/api/v2/member/dashboard/"


def pilot_config():
    config = default_config()
    for supported in config["supported_formats"]:
        for band in config["age_bands"]:
            config["references"][f"{supported}:{band['key']}"] = {
                "prior_rate": "0.1", "prior_views": "100", "baseline_floor": "1", "improvement_cap": "5",
                "response": [["0", "0"], ["1", "100"]],
                "improvement": [["0", "0"], ["5", "100"]],
                "popularity": [["0", "0"], ["1000", "100"]],
            }
    return config


@override_settings(LEAGUE_ENABLED=True)
class MemberDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email="dashboard@example.test", username="dashboard", password="Testing-123!", is_verified=True)
        cls.other = User.objects.create_user(email="other-dashboard@example.test", username="other-dashboard", password="Testing-123!", is_verified=True)
        cls.season = LeagueSeason.objects.create(year=2026)
        cls.version = ScoringVersion.objects.create(name="dashboard-test", config=pilot_config(), rules_confirmed=True,
                                                   calibrated=True, calibration_notes="Test fixtures only, not production calibration.")
        cls.product = Product(name="Figure", description="Figure", original_price="20.00", thumbnail="shop/test.png",
                              main_image="shop/test.png", redirect_url="https://example.test/figure")
        Product.objects.bulk_create([cls.product])

    def setUp(self):
        self.clock = patch("platform_api.member_views.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client.force_login(self.member)

    def week(self, start, state="finalized", revision=1, version=None):
        return CompetitionWeek.objects.create(season=self.season, scoring_version=version or self.version,
            start_at=start, cutoff_at=start + timedelta(days=5), scoring_date=(start + timedelta(days=4)).date(),
            state=state, current_revision=revision, finalized_at=start + timedelta(days=5) if state == "finalized" else None)

    def entry(self, week, user=None, state="active"):
        video_id = f"{CompetitionEntry.objects.count():011d}"
        return CompetitionEntry.objects.create(week=week, editor=user or self.member, platform="youtube", video_id=video_id,
            channel_id="channel", published_at=week.start_at - timedelta(days=2), canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            content_key=f"youtube:{video_id}", title=f"Edit {video_id}", state=state)

    def result(self, entry, points=25, rank=1, revision=None, effective=True):
        revision = revision if revision is not None else entry.week.current_revision
        result = WeeklyResult.objects.create(week=entry.week, entry=entry, revision=revision, placement=rank,
                                            league_points=points, weekly_score="80", snapshot=None, baseline=None)
        LeaguePointsAward.objects.create(week=entry.week, entry=entry, editor=entry.editor,
                                         revision=revision, points=points, effective=effective)
        return result

    def application(self, user=None, platform="youtube", **values):
        application = EditorApplication(user=user or self.member, channel_type=platform,
            channel_link=f"https://example.test/{uuid4()}", editing_area="transformers", **values)
        EditorApplication.objects.bulk_create([application])
        return application

    def test_private_read_only_and_empty_states(self):
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.client.force_login(self.member)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertIsNone(data["latest_edit"])
        self.assertIsNone(data["league"]["month"]["rank"])
        self.assertEqual(data["league"]["month"]["points"], 0)
        self.assertNotIn("season_standing", data["league"])
        self.assertEqual(data["applications"]["editors"], [])
        self.assertEqual(data["notifications"], {"unread_count": 0, "results": []})
        self.assertEqual(data["orders"], [])
        self.assertEqual(self.client.post(URL, {}, content_type="application/json").status_code, 405)
        for changes in ({"is_verified": False}, {"is_verified": True, "is_active": False}):
            get_user_model().objects.filter(pk=self.member.pk).update(**changes)
            self.assertEqual(self.client.get(URL).status_code, 401)

    def test_identity_honors_selected_channel_and_never_exposes_follower_rank(self):
        self.application(platform="youtube", status="accepted", channel_verified=True, channel_name="Huge channel", follower_count=900000, rank_position=1)
        self.application(platform="tiktok", status="accepted", channel_verified=True, channel_name="Chosen channel", channel_thumbnail="https://example.test/chosen.jpg", follower_count=2, rank_position=300)
        title = EditorTitle.objects.create(name="Cybertron Editor")
        get_user_model().objects.filter(pk=self.member.pk).update(profile_display_mode="channel", profile_channel_source="tiktok", selected_title=title,
                                                                 mix_rank_position=1, mix_rank_position_last_week=2)
        data = self.client.get(URL).json()
        self.assertEqual(data["member"]["display_name"], "Chosen channel")
        self.assertEqual(data["member"]["profile_picture"], "https://example.test/chosen.jpg")
        self.assertEqual(data["member"]["editor_title"], "Cybertron Editor")
        self.assertTrue(data["member"]["verified_editor"])
        self.assertEqual(data["member"]["verified_platforms"], ["tiktok", "youtube"])
        self.assertIsNone(data["league"]["month"]["rank"])
        self.assertIsNone(data["league"]["rank_change"])
        self.assertNotIn("follower", str(data))

    def test_only_current_official_revision_contributes_to_points_and_results(self):
        week = self.week(monday_for(NOW), revision=2)
        entry = self.entry(week)
        self.result(entry, points=99, rank=1, revision=1, effective=False)
        self.result(entry, points=16, rank=3, revision=2)
        # A stale award incorrectly left effective must still be excluded.
        stale = self.entry(self.week(monday_for(NOW) - timedelta(days=7), revision=2))
        self.result(stale, points=1000, revision=1)
        for offset, state in ((14, "exhibition"), (21, "canceled"), (28, "live")):
            self.result(self.entry(self.week(monday_for(NOW) - timedelta(days=offset), state=state)), points=700)
        data = self.client.get(URL).json()
        self.assertEqual(data["league"]["month"]["points"], 16)
        self.assertEqual(data["league"]["month"]["rank"], 1)
        self.assertEqual(data["league"]["latest_result"]["rank"], 3)
        self.assertEqual(data["edit_stats"]["league_points"], 16)
        self.assertEqual(data["edit_stats"]["best_league_result"], 3)

    def test_incomplete_or_invalid_scoring_configuration_is_neutral(self):
        week = self.week(monday_for(NOW))
        self.result(self.entry(week))
        for change in ({"rules_confirmed": False}, {"rules_confirmed": True, "config": default_config()}):
            ScoringVersion.objects.filter(pk=self.version.pk).update(**change)
            data = self.client.get(URL).json()
            self.assertIsNone(data["league"]["month"]["rank"])
            self.assertIsNone(data["league"]["latest_result"])
            self.assertIsNone(data["latest_edit"]["rank"])
            self.assertIsNone(data["edit_stats"]["league_points"])

    def test_next_round_deadline_and_entry_are_real_and_match_registration_rules(self):
        current = self.week(monday_for(NOW), state="live", revision=0)
        upcoming = self.week(next_week_start(NOW), state="scheduled", revision=0)
        current_entry, upcoming_entry = self.entry(current), self.entry(upcoming, state="queued")
        self.application(status="accepted", channel_verified=True)
        data = self.client.get(URL).json()
        self.assertTrue(data["league"]["can_submit"])
        self.assertEqual(data["league"]["submission_deadline"], "2026-10-05T00:00:00Z")
        self.assertEqual(data["league"]["current_entry"]["id"], current_entry.pk)
        self.assertEqual(data["league"]["next_entry"]["id"], upcoming_entry.pk)
        self.assertIsNone(data["latest_edit"]["league_points"])
        self.assertIn(upcoming_entry.video_id, data["latest_edit"]["thumbnail"])
        with override_settings(LEAGUE_ENABLED=False):
            self.assertFalse(self.client.get(URL).json()["league"]["can_submit"])

    def test_legacy_work_is_preserved_without_legacy_scoring(self):
        edit = EditSubmission(user=self.member, channel_type="youtube", channel_link="https://youtube.com/@test",
            video_url="https://youtube.com/shorts/abcdefghijk", title="Earlier creative work", status="verified",
            calculated_points="9999.00", week_rank=1, upvote_count=29)
        EditSubmission.objects.bulk_create([edit])
        data = self.client.get(URL).json()
        self.assertEqual(data["latest_edit"]["source"], "legacy")
        self.assertIsNone(data["latest_edit"]["rank"])
        self.assertIsNone(data["latest_edit"]["league_points"])
        self.assertEqual(data["latest_edit"]["upvotes"], 29)
        self.assertEqual(data["latest_edit"]["detail_url"], reverse("edithub:edit_submission_success", args=[edit.pk]))
        # The API test settings deliberately omit the legacy website templates.
        # Exercise the destination's ownership/status gates and render handoff.
        with patch("edithub.views.render", return_value=HttpResponse("Submission")) as render:
            self.assertEqual(self.client.get(data["latest_edit"]["detail_url"]).status_code, 200)
        self.assertEqual(render.call_args.args[1], "edithub/edit_submission_success.html")
        self.assertEqual(render.call_args.args[2]["submission"].pk, edit.pk)
        self.assertEqual(data["edit_stats"]["legacy_verified"], 1)
        self.assertEqual(data["edit_stats"]["legacy_upvotes"], 29)
        self.assertIsNone(data["edit_stats"]["league_points"])
        self.assertNotIn("9999", str(data))

    def test_latest_preview_follows_submission_time_across_both_existing_sources(self):
        entry = self.entry(self.week(monday_for(NOW), state="live", revision=0))
        edit = EditSubmission(user=self.member, channel_type="youtube", channel_link="https://youtube.com/@test",
            video_url="https://youtube.com/shorts/abcdefghijk", title="More recent work", status="pending")
        EditSubmission.objects.bulk_create([edit])
        CompetitionEntry.objects.filter(pk=entry.pk).update(created_at=NOW - timedelta(days=2))
        EditSubmission.objects.filter(pk=edit.pk).update(submitted_date=NOW - timedelta(days=1))
        latest = self.client.get(URL).json()["latest_edit"]
        self.assertEqual(latest["source"], "legacy")
        self.assertEqual(latest["detail_url"], reverse("edithub:preview_edit_submission", args=[edit.pk]))
        EditSubmission.objects.filter(pk=edit.pk).update(status="rejected")
        self.assertEqual(self.client.get(URL).json()["latest_edit"]["detail_url"], edit.video_url)
        CompetitionEntry.objects.filter(pk=entry.pk).update(created_at=NOW)
        latest = self.client.get(URL).json()["latest_edit"]
        self.assertEqual(latest["source"], "league")
        self.assertEqual(latest["id"], entry.pk)

    def test_other_members_records_are_excluded_and_previews_are_bounded(self):
        for user in (self.member, self.other):
            self.application(user, status="pending", channel_name=f"{user.username} channel")
            Notification.objects.bulk_create([Notification(user=user, title=f"{user.username} notification", message="Review", notification_type="edit_verified") for _ in range(6)])
            for index in range(5):
                event = Event.objects.create(title=f"{user.username} event {index}", description="Details", created_by=self.member, deadline=NOW, date=NOW)
                EventApplication.objects.bulk_create([EventApplication(event=event, applicant=user, status="accepted", cover_letter="Private application text")])
                PaymentOrder.objects.create(user=user, product=self.product, idempotency_key=uuid4(), product_name=f"{user.username} item",
                    stripe_price_id="price_test", stripe_product_id="prod_test", amount_minor=2000, currency="usd",
                    fulfillment_kind="physical", fulfillment_note="Delivery details", fulfillment_admin_note="Private staff details")
        data = self.client.get(URL + f"?user_id={self.other.pk}").json()
        self.assertEqual(len(data["orders"]), 3)
        self.assertEqual(len(data["notifications"]["results"]), 4)
        self.assertEqual(data["notifications"]["unread_count"], 6)
        self.assertEqual(len(data["applications"]["events"]), 3)
        self.assertEqual(data["applications"]["event_count"], 5)
        self.assertNotIn("other-dashboard", str(data))
        self.assertNotIn("Private", str(data))
        self.assertNotIn("stripe_price_id", str(data))
        self.assertTrue(data["orders"][0]["url"].startswith("/account/orders/"))

    def test_legacy_follower_ranking_notices_stay_out_of_v2_preview(self):
        Notification.objects.bulk_create([
            Notification(user=self.member, title="Legacy follower ranking", message="Your follower rank is #1", notification_type="ranking_updated"),
            Notification(user=self.member, title="Application reviewed", message="Application approved", notification_type="application_approved"),
        ])
        notices = self.client.get(URL).json()["notifications"]
        self.assertEqual(notices["unread_count"], 2)
        self.assertEqual([notice["title"] for notice in notices["results"]], ["Application reviewed"])
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 2)

    def test_aggregate_query_count_does_not_grow_per_award_and_ties_are_preserved(self):
        week = self.week(monday_for(NOW))
        self.result(self.entry(week), points=25, rank=1)
        with CaptureQueriesContext(connection) as first:
            first_rows = services.aggregate_standings(2026)
        self.result(self.entry(week, self.other), points=25, rank=1)
        with CaptureQueriesContext(connection) as second:
            second_rows = services.aggregate_standings(2026)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), len(first))
        self.assertEqual(first_rows[0]["points"], 25)
        self.assertEqual([row["rank"] for row in second_rows], [1, 1])
