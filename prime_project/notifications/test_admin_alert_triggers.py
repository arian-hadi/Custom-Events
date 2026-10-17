"""Lifecycle trigger tests; delivery itself is tested by the outbox test suite."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.db.models.signals import post_save
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from edithub.models import EditReport, EditSubmission, EditorApplication
from events.models import Event, EventApplication, EventField, EventFieldResponse
from notifications.models import AdminEmailDelivery


class AdminAlertTriggerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(
            email="trigger-member@example.test", username="trigger-member", password="Test-passphrase-927", is_verified=True,
        )
        cls.organizer = get_user_model().objects.create_user(
            email="trigger-organizer@example.test", username="trigger-organizer", password="Test-passphrase-927", role="admin", is_verified=True,
        )
        cls.event = Event.objects.create(
            title="Trigger event", description="Test", created_by=cls.organizer,
            deadline=timezone.now() + timedelta(days=1), date=timezone.now() + timedelta(days=2),
        )

    def setUp(self):
        self.queue_patch = patch("notifications.signals.queue_admin_alert")
        self.queue = self.queue_patch.start()
        self.addCleanup(self.queue_patch.stop)
        self.sequence = 0

    def application(self, **changes):
        self.sequence += 1
        values = {
            "user": self.member, "channel_type": "youtube",
            "channel_link": f"https://www.youtube.com/@trigger-{self.sequence}",
            "editing_area": "transformers", "data_consent": True,
        }
        values.update(changes)
        return EditorApplication.objects.create(**values)

    def submission(self, **changes):
        self.sequence += 1
        values = {
            "user": self.member, "channel_type": "youtube", "channel_link": "https://www.youtube.com/@trigger",
            "video_url": f"https://www.youtube.com/shorts/trigger-{self.sequence}",
            "scheduled_week": (timezone.now() + timedelta(days=7)).date(),
        }
        values.update(changes)
        return EditSubmission.objects.create(**values)

    def test_editor_application_alert_waits_for_actual_confirmation(self):
        application = self.application()
        self.queue.assert_not_called()
        self.client.force_login(self.member)
        session = self.client.session
        session["pending_application_ids"] = [application.pk]
        session.save()
        response = self.client.post("/editinghub/confirm/", {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.queue.assert_called_once()
        self.assertEqual(self.queue.call_args.args[0], "editor_application")
        self.assertEqual(self.queue.call_args.args[1].pk, application.pk)
        application.refresh_from_db()
        self.assertTrue(application.channel_verified)
        application.channel_name = "Updated metadata"
        application.save()
        self.assertEqual(self.queue.call_count, 1)

    def test_cancelled_editor_draft_and_reviewed_creation_do_not_alert(self):
        draft = self.application()
        draft.delete()
        with patch.object(EditorApplication, "update_rank_positions"):
            self.application(channel_verified=True, status="accepted")
        self.queue.assert_not_called()

    def test_new_confirmed_pending_application_alerts_once(self):
        application = self.application(channel_verified=True)
        self.queue.assert_called_once_with("editor_application", application)
        application.save(update_fields=["channel_verified"])
        self.assertEqual(self.queue.call_count, 1)

    def test_unsaved_confirmation_attribute_does_not_trigger_partial_save(self):
        application = self.application()
        application.channel_verified = True
        application.channel_name = "Metadata"
        application.save(update_fields=["channel_name"])
        application.save(update_fields=["status"])
        self.queue.assert_not_called()
        application.refresh_from_db()
        self.assertFalse(application.channel_verified)

    def test_removal_requires_false_to_true_transition_on_existing_record(self):
        application = self.application()
        application.removal_requested = True
        application.removal_requested_date = timezone.now()
        application.save(update_fields=["removal_requested", "removal_requested_date"])
        self.queue.assert_called_once_with("editor_removal", application)
        application.save()
        self.assertEqual(self.queue.call_count, 1)
        self.queue.reset_mock()
        self.application(removal_requested=True)
        self.queue.assert_not_called()

    def test_edit_submission_preview_confirmation_not_draft_save_alerts(self):
        submission = self.submission()
        self.queue.assert_not_called()
        self.client.force_login(self.member)
        response = self.client.post(f"/editinghub/edit-submission/{submission.pk}/preview/", {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.queue.assert_called_once()
        self.assertEqual(self.queue.call_args.args[0], "edit_submission")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "verified")
        self.assertIsNotNone(submission.verified_date)
        submission.title = "Updated title"
        submission.save()
        submission.report_count = 1
        submission.save(update_fields=["report_count"])
        self.assertEqual(self.queue.call_count, 1)

    def test_legacy_edit_confirmation_path_uses_persisted_verified_status(self):
        submission = self.submission()
        self.client.force_login(self.member)
        session = self.client.session
        session["pending_edit_submission_id"] = submission.pk
        session.save()
        response = self.client.post("/editinghub/confirm-edit/", {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.queue.assert_called_once()
        self.assertEqual(self.queue.call_args.args[0], "edit_submission")

    def test_rejected_and_cancelled_draft_edits_do_not_alert(self):
        submission = self.submission()
        submission.status = "rejected"
        submission.save(update_fields=["status"])
        submission.delete()
        self.queue.assert_not_called()

    def test_stale_unsaved_verified_status_does_not_alert(self):
        submission = self.submission()
        submission.status = "verified"
        submission.title = "Preview only"
        submission.save(update_fields=["title"])
        self.queue.assert_not_called()

    def test_active_new_report_alerts_once_and_resolution_does_not_alert(self):
        submission = self.submission()
        report = EditReport.objects.create(user=self.member, edit_submission=submission, reason="spam", description="Details")
        self.queue.assert_called_once_with("edit_report", report)
        report.is_resolved = True
        report.save(update_fields=["is_resolved"])
        report.description = "More detail"
        report.save()
        self.assertEqual(self.queue.call_count, 1)
        self.queue.reset_mock()
        EditReport.objects.create(user=self.member, edit_submission=self.submission(), reason="other", is_active=False)
        self.queue.assert_not_called()

    def test_new_event_application_only_and_fixture_signals_are_ignored(self):
        application = EventApplication.objects.create(event=self.event, applicant=self.member)
        self.queue.assert_called_once_with("event_application", application)
        application.status = "reviewing"
        application.save(update_fields=["status"])
        self.assertEqual(self.queue.call_count, 1)
        self.queue.reset_mock()
        post_save.send(sender=EventApplication, instance=application, created=True, raw=True, using="default", update_fields=None)
        self.queue.assert_not_called()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMIN_NOTIFICATION_RECIPIENTS="reviewer@example.test",
    ADMIN_NOTIFICATION_BASE_URL="https://website.example.test",
    ADMIN_EMAIL_SEND_IMMEDIATELY=True,
)
class AdminAlertCommitTests(TransactionTestCase):
    """Use real commits so missing view-level atomic blocks cannot hide in TestCase."""

    def setUp(self):
        self.member = get_user_model().objects.create_user(
            email="commit-member@example.test", username="commit-member", password="Test-passphrase-927", is_verified=True,
        )
        organizer = get_user_model().objects.create_user(email="commit-organizer@example.test", username="commit-organizer", role="admin")
        self.event = Event.objects.create(
            title="Committed event", description="Test", created_by=organizer,
            deadline=timezone.now() + timedelta(days=1), date=timezone.now() + timedelta(days=2),
        )
        self.field = EventField.objects.create(event=self.event, name="Entry", field_type="text")
        self.client.force_login(self.member)

    def observe_commit(self, kind, instance):
        self.assertEqual(kind, "event_application")
        self.assertTrue(transaction.get_connection().in_atomic_block)
        transaction.on_commit(lambda: self.answers_at_delivery.append(
            list(EventFieldResponse.objects.filter(application_id=instance.pk).values_list("value_text", flat=True))
        ))

    def test_legacy_application_answers_exist_before_delivery_callback(self):
        self.answers_at_delivery = []
        with patch("notifications.signals.queue_admin_alert", side_effect=self.observe_commit) as queue:
            response = self.client.post(f"/events/events/{self.event.pk}/apply/", {f"field_{self.field.pk}": "Legacy answer"})
        self.assertEqual(response.status_code, 302)
        queue.assert_called_once()
        self.assertEqual(self.answers_at_delivery, [["Legacy answer"]])

    def test_v2_application_answers_exist_before_delivery_callback(self):
        self.answers_at_delivery = []
        with patch("notifications.signals.queue_admin_alert", side_effect=self.observe_commit) as queue:
            response = self.client.post(f"/api/v2/events/{self.event.pk}/apply/", {f"field_{self.field.pk}": "V2 answer"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        queue.assert_called_once()
        self.assertEqual(self.answers_at_delivery, [["V2 answer"]])

    def test_failed_legacy_answer_save_rolls_back_application_and_commit_alert(self):
        self.answers_at_delivery = []
        with patch("notifications.signals.queue_admin_alert", side_effect=self.observe_commit):
            with patch.object(EventFieldResponse, "save", side_effect=RuntimeError("Synthetic answer failure")):
                with self.assertRaises(RuntimeError):
                    self.client.post(f"/events/events/{self.event.pk}/apply/", {f"field_{self.field.pk}": "Answer"})
        self.assertFalse(EventApplication.objects.exists())
        self.assertEqual(self.answers_at_delivery, [])

    def assert_delivered_answer(self, answer):
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reviewer@example.test"])
        self.assertIn(f"Entry: {answer}", mail.outbox[0].body)
        delivery = AdminEmailDelivery.objects.get()
        self.assertEqual(delivery.kind, "event_application")
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(delivery.attempts, 1)
        self.assertIn(f"Entry: {answer}", delivery.body)

    def test_real_v2_alert_includes_answers_and_duplicate_attempt_sends_nothing(self):
        url = f"/api/v2/events/{self.event.pk}/apply/"
        payload = {f"field_{self.field.pk}": "V2 complete answer"}
        response = self.client.post(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assert_delivered_answer("V2 complete answer")
        response = self.client.post(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assert_delivered_answer("V2 complete answer")
        self.assertEqual(EventApplication.objects.count(), 1)

    def test_real_legacy_alert_includes_answers_after_commit(self):
        response = self.client.post(
            f"/events/events/{self.event.pk}/apply/",
            {f"field_{self.field.pk}": "Legacy complete answer"},
        )
        self.assertEqual(response.status_code, 302)
        self.assert_delivered_answer("Legacy complete answer")

    def test_real_editor_confirmation_sends_only_when_ready(self):
        application = EditorApplication.objects.create(
            user=self.member, channel_type="youtube", channel_link="https://www.youtube.com/@commit-editor",
            channel_name="Confirmed editor", editing_area="transformers", data_consent=True,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(AdminEmailDelivery.objects.exists())
        session = self.client.session
        session["pending_application_ids"] = [application.pk]
        session.save()
        response = self.client.post("/editinghub/confirm/", {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertTrue(application.channel_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reviewer@example.test"])
        self.assertIn("Channel: Confirmed editor", mail.outbox[0].body)
        self.assertIn(self.member.email, mail.outbox[0].body)
        delivery = AdminEmailDelivery.objects.get()
        self.assertEqual(delivery.kind, "editor_application")
        self.assertEqual(delivery.status, "sent")
