from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from edithub.models import EditorApplication, EditSubmission, EditReport
from events.models import Event, EventApplication, EventField, EventFieldResponse
from .admin_email import queue_admin_alert, safely_deliver, recipients_for, configuration
from .models import AdminEmailDelivery, AdminEmailSettings


@override_settings(
    ADMIN_NOTIFICATION_RECIPIENTS='owner@example.test',
    ADMIN_NOTIFICATION_BASE_URL='https://website.example.test',
    ADMIN_EMAIL_SEND_IMMEDIATELY=False,
)
class AdminEmailTests(TestCase):
    def setUp(self):
        self.member = get_user_model().objects.create_user(
            email='applicant@example.test', username='Applicant <script>', password='Local-Test-Password-741',
            is_active=True, is_verified=True,
        )

    def application(self):
        item = EditorApplication.objects.create(
            user=self.member, channel_link='https://example.test/channel', channel_type='youtube',
            channel_name='Local channel <script>alert(1)</script>', editing_area='other',
            editing_tool='Test editor', data_consent=True, channel_verified=False,
        )
        # Service tests arrange a persisted, ready record without depending on signal dispatch.
        EditorApplication.objects.filter(pk=item.pk).update(channel_verified=True)
        item.refresh_from_db()
        return item

    def queued(self):
        item = self.application()
        queue_admin_alert('editor_application', item)
        return item, AdminEmailDelivery.objects.get()

    def test_unique_alert_for_each_recipient_and_safe_complete_message(self):
        item, row = self.queued()
        queue_admin_alert('editor_application', item)
        self.assertEqual(AdminEmailDelivery.objects.count(), 1)
        self.assertTrue(safely_deliver(row.pk))
        self.assertFalse(safely_deliver(row.pk))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['owner@example.test'])
        self.assertIn('applicant@example.test', message.body)
        self.assertIn(item.channel_link, message.body)
        self.assertIn(f'https://website.example.test/admin/edithub/editorapplication/{item.pk}/change/', message.body)
        html = message.alternatives[0][0]
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        row.refresh_from_db()
        self.assertEqual(row.status, 'sent')
        self.assertEqual(row.attempts, 1)

    @override_settings(ADMIN_EMAIL_SEND_IMMEDIATELY=True)
    def test_email_is_sent_after_commit_and_queue_rolls_back_with_submission(self):
        item = self.application()
        with self.captureOnCommitCallbacks(execute=True):
            queue_admin_alert('editor_application', item)
            self.assertEqual(len(mail.outbox), 0)
            self.assertEqual(AdminEmailDelivery.objects.get().status, 'pending')
        self.assertEqual(len(mail.outbox), 1)
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    queue_admin_alert('editor_removal', item)
                    raise RuntimeError('Roll back this operation')
        self.assertEqual(AdminEmailDelivery.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_disabled_topics_and_recipient_changes_are_respected(self):
        item = self.application()
        config = AdminEmailSettings.objects.create(editor_application=False)
        queue_admin_alert('editor_application', item)
        self.assertFalse(AdminEmailDelivery.objects.exists())
        config.editor_application = True
        config.recipients = 'NEW@example.test, new@example.test; second@example.test'
        config.save()
        queue_admin_alert('editor_application', item)
        self.assertEqual(AdminEmailDelivery.objects.count(), 2)
        config.enabled = False
        config.save()
        for row in AdminEmailDelivery.objects.all():
            self.assertFalse(safely_deliver(row.pk))
        self.assertEqual(set(AdminEmailDelivery.objects.values_list('status', flat=True)), {'cancelled'})
        self.assertEqual(len(mail.outbox), 0)

    def test_removed_recipient_and_no_longer_pending_application_are_cancelled(self):
        item, row = self.queued()
        AdminEmailSettings.objects.create(recipients='replacement@example.test')
        self.assertFalse(safely_deliver(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'cancelled')
        queue_admin_alert('editor_application', item)
        new_row = AdminEmailDelivery.objects.get(recipient='replacement@example.test')
        EditorApplication.objects.filter(pk=item.pk).update(status='rejected')
        self.assertFalse(safely_deliver(new_row.pk))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ADMIN_NOTIFICATION_RECIPIENTS='')
    def test_fallback_only_active_superusers_not_applicants_or_other_staff(self):
        User = get_user_model()
        User.objects.create_user(email='staff@example.test', username='staff', is_staff=True)
        User.objects.create_user(email='inactive@example.test', username='inactive', is_superuser=True, is_active=False)
        User.objects.create_superuser(email='owner@example.test', username='owner', password='Test-Password-918')
        self.assertEqual(recipients_for(configuration()), ['owner@example.test'])

    @override_settings(ADMIN_NOTIFICATION_RECIPIENTS='')
    def test_no_recipients_does_not_guess_or_send_to_applicant(self):
        queue_admin_alert('editor_application', self.application())
        self.assertFalse(AdminEmailDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_delivery_failure_keeps_submission_and_can_be_retried_when_due(self):
        item, row = self.queued()
        with patch('notifications.admin_email.EmailMultiAlternatives.send', side_effect=OSError('private server detail')):
            self.assertFalse(safely_deliver(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed')
        self.assertNotIn('private server detail', row.last_error)
        self.assertTrue(EditorApplication.objects.filter(pk=item.pk).exists())
        output = StringIO()
        call_command('send_admin_alerts', stdout=output)
        self.assertEqual(len(mail.outbox), 0)
        AdminEmailDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        call_command('send_admin_alerts', stdout=output)
        row.refresh_from_db()
        self.assertEqual(row.status, 'sent')
        self.assertEqual(row.attempts, 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_console_and_unapproved_file_backends_are_not_reported_as_sent(self):
        _, row = self.queued()
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            self.assertFalse(safely_deliver(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed')
        self.assertEqual(len(mail.outbox), 0)

    def test_file_capture_requires_local_preview_and_records_captured_status(self):
        _, row = self.queued()
        with TemporaryDirectory() as directory:
            with override_settings(EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend', EMAIL_FILE_PATH=directory, V2_LOCAL_PREVIEW=False):
                self.assertFalse(safely_deliver(row.pk))
                self.assertEqual(list(Path(directory).iterdir()), [])
            AdminEmailDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
            with override_settings(EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend', EMAIL_FILE_PATH=directory, V2_LOCAL_PREVIEW=True):
                self.assertTrue(safely_deliver(row.pk))
            row.refresh_from_db()
            self.assertEqual(row.status, 'captured')
            self.assertEqual(len(list(Path(directory).glob('*.log'))), 1)

    def test_invalid_origin_fails_without_sending(self):
        _, row = self.queued()
        with override_settings(ADMIN_NOTIFICATION_BASE_URL='https://user:password@example.test'):
            self.assertFalse(safely_deliver(row.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_interrupted_recovery_skips_recent_active_claims(self):
        _, row = self.queued()
        model_admin = admin.site._registry[AdminEmailDelivery]
        self.member.is_superuser = True
        request = SimpleNamespace(user=self.member)
        AdminEmailDelivery.objects.filter(pk=row.pk).update(status='sending', updated_at=timezone.now())
        with patch.object(model_admin, 'message_user'):
            with self.captureOnCommitCallbacks(execute=True):
                model_admin.retry_interrupted(request, AdminEmailDelivery.objects.filter(pk=row.pk))
            self.assertEqual(len(mail.outbox), 0)
            AdminEmailDelivery.objects.filter(pk=row.pk).update(updated_at=timezone.now()-timedelta(minutes=16))
            with self.captureOnCommitCallbacks(execute=True):
                model_admin.retry_interrupted(request, AdminEmailDelivery.objects.filter(pk=row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'sent')
        self.assertEqual(len(mail.outbox), 1)

    def test_invalid_recipient_and_non_owner_settings_access_are_rejected(self):
        with self.assertRaises(ValidationError):
            AdminEmailSettings(recipients='not-an-email').full_clean()
        self.member.is_staff = True
        self.member.save(update_fields=['is_staff'])
        self.client.force_login(self.member)
        for model in ('adminemailsettings', 'adminemaildelivery'):
            self.assertEqual(self.client.get(f'/admin/notifications/{model}/').status_code, 403)

    def test_other_alert_kinds_render_the_relevant_details(self):
        config = AdminEmailSettings.objects.create(enabled=False)
        application = self.application()
        application.removal_requested = True
        application.save(update_fields=['removal_requested'])
        edit = EditSubmission.objects.create(user=self.member, channel_type='youtube',
            channel_link='https://example.test/channel', video_url='https://example.test/video',
            title='Test edit', status='verified')
        report = EditReport.objects.create(user=self.member, edit_submission=edit, reason='spam', description='Report details')
        event = Event.objects.create(title='Test event', description='Example', created_by=self.member,
            deadline=timezone.now()+timedelta(days=1), date=timezone.now()+timedelta(days=2))
        entry = EventApplication.objects.create(applicant=self.member, event=event)
        field = EventField.objects.create(event=event, name='Entry link', field_type='text')
        EventFieldResponse.objects.create(application=entry, field=field, value_text='https://example.test/entry')
        config.enabled = True
        config.save()
        for kind, item in [('editor_removal', application), ('edit_submission', edit), ('edit_report', report), ('event_application', entry)]:
            queue_admin_alert(kind, item)
        for row in AdminEmailDelivery.objects.all():
            self.assertTrue(safely_deliver(row.pk), row.kind)
        self.assertEqual(len(mail.outbox), 4)
        event_mail = next(message for message in mail.outbox if 'New event application' in message.subject)
        self.assertIn('Entry link: https://example.test/entry', event_mail.body)
