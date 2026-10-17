"""Cross-feature acceptance: all email uses Django's isolated memory backend."""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from edithub.league import services
from edithub.league_models import CompetitionEntry, ScoringVersion
from edithub.test_league_core import START, fixture_config
from events.models import Event, EventApplication
from notifications.activity_email import deliver_activity_email, unsubscribe_token
from notifications.activity_email import delivery_state
from notifications.campaigns import public_origin
from notifications.league_activity import process_pending_league_events
from notifications.manager import notification_manager
from notifications.models import LeagueNotificationEvent, MemberActivityDelivery, Notification, NotificationPreference


@override_settings(MEMBER_ACTIVITY_EMAIL_ENABLED=True, MEMBER_EMAIL_ENABLED=False,
    MEMBER_EMAIL_BASE_URL='https://community.example.test', V2_TRUST_GATEWAY_ADDRESS=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', ADMIN_EMAIL_SEND_IMMEDIATELY=False)
class ActivityIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='member@example.test', username='activity-member', is_verified=True)
        self.client.force_login(self.user)

    def queue(self, kind='application_approved', key='test-event'):
        return notification_manager.create_notification(self.user, 'An update', 'Your application is approved.', kind, event_key=key)

    def test_single_event_is_queued_once_and_worker_works_without_campaigns(self):
        notice = self.queue()
        self.queue()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(MemberActivityDelivery.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        call_command('member_email_tick', stdout=StringIO())
        row = MemberActivityDelivery.objects.get(notification=notice)
        self.assertEqual(row.status, 'sent')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('List-Unsubscribe-Post', mail.outbox[0].extra_headers)
        self.assertFalse(deliver_activity_email(row.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_preference_patch_cancels_pending_activity_and_link_is_v2(self):
        notice = self.queue()
        response = self.client.patch('/api/v2/notification-preferences/', {'email_application_updates': False}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['email_activity_delivery_active'])
        row = MemberActivityDelivery.objects.get(notification=notice)
        self.assertEqual(row.status, 'cancelled')
        self.assertFalse(deliver_activity_email(row.pk))

    def test_delivery_rechecks_address_and_global_master_switch(self):
        self.queue()
        row = MemberActivityDelivery.objects.get()
        NotificationPreference.objects.filter(user=self.user).update(email_enabled=False)
        self.assertFalse(deliver_activity_email(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'cancelled')
        self.assertEqual(len(mail.outbox), 0)

    def test_unsubscribe_get_is_safe_and_signed_post_turns_off_optional_emails(self):
        self.queue()
        token = unsubscribe_token(self.user)
        url = reverse('member_email:activity_unsubscribe', args=[token])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(NotificationPreference.objects.get(user=self.user).email_enabled)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(NotificationPreference.objects.get(user=self.user).email_enabled)
        self.assertEqual(MemberActivityDelivery.objects.get().status, 'cancelled')
        self.assertEqual(self.client.post(reverse('member_email:activity_one_click', args=['invalid']), {'List-Unsubscribe': 'One-Click'}).status_code, 400)

    @patch('notifications.activity_email.EmailMultiAlternatives.send', side_effect=OSError('private provider detail'))
    def test_failure_retries_without_exposing_provider_details(self, send):
        self.queue()
        row = MemberActivityDelivery.objects.get()
        self.assertFalse(deliver_activity_email(row.pk))
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), ('failed', 1))
        self.assertNotIn('private provider detail', row.last_error)
        self.assertGreater(row.next_attempt_at, timezone.now())
        self.assertFalse(deliver_activity_email(row.pk))
        self.assertEqual(send.call_count, 1)

    def test_save_decision_signals_cover_admin_and_do_not_repeat_unchanged_state(self):
        event = Event.objects.create(title='Event', created_by=self.user, deadline=timezone.now() + timedelta(days=3), date=timezone.now() + timedelta(days=5))
        application = EventApplication.objects.create(event=event, applicant=self.user)
        application.status = 'accepted'
        application.save(update_fields=['status'])
        application.save(update_fields=['status'])
        self.assertEqual(Notification.objects.filter(notification_type='application_approved').count(), 1)
        self.assertEqual(MemberActivityDelivery.objects.count(), 1)
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['results'][0]['url'], f'/applications/events/{application.pk}')

    def test_rollback_does_not_leave_email_or_notification(self):
        try:
            with transaction.atomic():
                self.queue()
                raise ValueError('rollback')
        except ValueError:
            pass
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(MemberActivityDelivery.objects.count(), 0)

    def test_disabled_gate_does_not_create_backlog_or_follower_emails(self):
        with override_settings(MEMBER_ACTIVITY_EMAIL_ENABLED=False):
            self.queue()
        self.queue('ranking_updated', 'legacy-ranking')
        call_command('member_email_tick', stdout=StringIO())
        self.assertEqual(MemberActivityDelivery.objects.count(), 0)
        self.assertFalse(Notification.objects.filter(notification_type='ranking_updated').exists())

    @override_settings(DEBUG=True, MEMBER_EMAIL_BASE_URL='http://localhost:8082',
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='mailpit')
    def test_docker_loopback_origin_and_mailpit_are_reported_as_local_capture(self):
        self.assertEqual(public_origin(), 'http://localhost:8082')
        self.assertEqual(delivery_state(), {'email_activity_delivery_active': False, 'email_activity_capture_mode': True})
        with override_settings(EMAIL_HOST='smtp.gmail.com'):
            self.assertTrue(delivery_state()['email_activity_delivery_active'])
        with override_settings(MEMBER_EMAIL_BASE_URL='http://remote.example.test'):
            with self.assertRaises(ValueError):
                public_origin()

    def test_official_revision_events_recover_once_and_corrections_replace_pending_mail(self):
        version = ScoringVersion.objects.create(name='email-test-only', config=fixture_config(), rules_confirmed=True,
            calibrated=True, calibration_notes='Synthetic isolated fixture; never a production calibration.')
        week = services.ensure_week(START, version)
        entries = []
        for index in range(5):
            user = self.user if index == 0 else get_user_model().objects.create_user(email=f'editor{index}@example.test', username=f'editor{index}', is_verified=True)
            entries.append(CompetitionEntry.objects.create(week=week, editor=user, platform='youtube', video_id=f'fixture-{index}',
                channel_id=f'channel-{index}', video_format='short', published_at=week.cutoff_at - timedelta(days=30), canonical_url=f'https://www.youtube.com/watch?v=fixture-{index}'))
        week = services.activate_week(week, now=week.start_at)
        completed = week.cutoff_at - timedelta(minutes=1)
        with patch('edithub.league.services.timezone.now', return_value=completed):
            for index, entry in enumerate(entries):
                services.record_snapshot(entry, {'likes': 500 - index * 50, 'views': 10000, 'completed_at': completed, 'provider': 'isolated-fixture'})
        services.finalize_week(week, now=week.cutoff_at)
        self.assertEqual(LeagueNotificationEvent.objects.filter(processed_at=None).count(), 1)
        self.assertEqual(process_pending_league_events(), 1)
        self.assertEqual(process_pending_league_events(), 0)
        self.assertEqual(Notification.objects.filter(notification_type='league_result').count(), 5)
        self.assertEqual(Notification.objects.filter(notification_type='league_award').count(), 1)
        original_ids = list(MemberActivityDelivery.objects.values_list('pk', flat=True))
        admin = get_user_model().objects.create_user(email='admin@example.test', username='email-admin', is_staff=True, is_superuser=True)
        services.correct_week(week, reason='Disqualification after review', actor=admin, disqualified_entry_ids=[entries[0].pk], now=week.cutoff_at)
        process_pending_league_events()
        self.assertFalse(MemberActivityDelivery.objects.filter(pk__in=original_ids, status='pending').exists())
        self.assertEqual(Notification.objects.filter(notification_type='league_result').count(), 10)

    def league_round(self, start=START, users=None):
        version, _ = ScoringVersion.objects.get_or_create(name='lead-email-fixture', defaults=dict(
            config=fixture_config(), rules_confirmed=True, calibrated=True, calibration_notes='Synthetic test fixture.'))
        week = services.ensure_week(start, version)
        if users is None:
            users = [self.user] + [get_user_model().objects.create_user(email=f'lead{i}@example.test', username=f'lead{i}', is_verified=True) for i in range(4)]
        entries = [CompetitionEntry.objects.create(week=week, editor=user, platform='youtube',
            video_id=f'lead-{week.pk}-{i}', channel_id=f'channel-{i}', video_format='short',
            published_at=week.cutoff_at-timedelta(days=30)) for i, user in enumerate(users)]
        week = services.activate_week(week, now=week.start_at)
        completed = week.cutoff_at-timedelta(minutes=2)
        with patch('edithub.league.services.timezone.now', return_value=completed):
            for i, entry in enumerate(entries):
                services.record_snapshot(entry, dict(likes=500-i*50, views=10000, completed_at=completed, provider='fixture'))
        return week, entries, completed

    def test_weekly_first_lead_is_once_per_editor_per_week_and_respects_preferences(self):
        from notifications.league_activity import notify_provisional_leader
        week, entries, moment = self.league_round()
        self.assertTrue(notify_provisional_leader(week.pk, now=moment))
        self.assertFalse(notify_provisional_leader(week.pk, now=moment))
        self.assertEqual(MemberActivityDelivery.objects.count(), 1)
        later = moment+timedelta(seconds=30)
        with patch('edithub.league.services.timezone.now', return_value=later):
            services.record_snapshot(entries[1], dict(likes=900, views=10000, completed_at=later, provider='fixture'))
        self.assertTrue(notify_provisional_leader(week.pk, now=later))
        self.assertEqual(MemberActivityDelivery.objects.count(), 2)
        later += timedelta(seconds=30)
        with patch('edithub.league.services.timezone.now', return_value=later):
            services.record_snapshot(entries[0], dict(likes=1000, views=10000, completed_at=later, provider='fixture'))
        self.assertFalse(notify_provisional_leader(week.pk, now=later))
        services.finalize_week(week, now=week.cutoff_at)
        process_pending_league_events()
        self.assertEqual(MemberActivityDelivery.objects.filter(status='pending').count(), 5)
        self.assertEqual(Notification.objects.filter(event_key__startswith='league:monthly-lead:').count(), 1)
        self.assertIn('monthly league', MemberActivityDelivery.objects.get(user=self.user, status='pending').body)
        self.assertFalse(MemberActivityDelivery.objects.filter(notification__title='League standing updated').exists())
        self.assertFalse(notify_provisional_leader(week.pk, now=week.cutoff_at))
        second, _, second_moment = self.league_round(start=START+timedelta(days=7), users=[entry.editor for entry in entries])
        NotificationPreference.objects.filter(user=self.user).update(email_ranking_updates=False)
        self.assertTrue(notify_provisional_leader(second.pk, now=second_moment))
        self.assertFalse(MemberActivityDelivery.objects.filter(notification__event_key=f'league:weekly-lead:{second.pk}:{self.user.pk}').exists())

    def test_missing_provider_data_does_not_announce_a_partial_leader(self):
        from notifications.league_activity import notify_provisional_leader
        week, entries, moment = self.league_round()
        entries[-1].snapshots.all().delete()
        self.assertFalse(notify_provisional_leader(week.pk, now=moment))
        self.assertFalse(MemberActivityDelivery.objects.exists())

    def test_branded_email_escapes_member_content_and_keeps_text_and_unsubscribe(self):
        notice = notification_manager.create_notification(self.user, 'Title <script>', '<img src=x onerror=bad()>',
            'application_approved', event_key='html-escape')
        row = MemberActivityDelivery.objects.get(notification=notice)
        self.assertTrue(deliver_activity_email(row.pk))
        message = mail.outbox[-1]
        html, mime = message.alternatives[0]
        self.assertEqual(mime, 'text/html')
        self.assertIn('<table', html)
        self.assertIn('2.0Transformers', html)
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('<img src=x', message.body)
        self.assertIn('List-Unsubscribe', message.extra_headers)

    def test_monthly_first_lead_is_not_repeated_until_a_new_month(self):
        week, entries, _ = self.league_round(start=START-timedelta(days=7))
        users = [entry.editor for entry in entries]
        for week_start in [START-timedelta(days=7), START, START+timedelta(days=7)]:
            if week_start != week.start_at:
                week, _, _ = self.league_round(start=week_start, users=users)
            services.finalize_week(week, now=week.cutoff_at)
            process_pending_league_events()
            process_pending_league_events()
        self.assertEqual(Notification.objects.filter(event_key__startswith='league:monthly-lead:2026-07:').count(), 1)
        self.assertEqual(Notification.objects.filter(event_key__startswith='league:monthly-lead:2026-08:').count(), 1)
        self.assertEqual(MemberActivityDelivery.objects.count(), 15)
        self.assertEqual(MemberActivityDelivery.objects.filter(user=self.user, body__contains='also reached #1').count(), 2)
