from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from platform_api.models import BlogPost
from shop.models import Product
from .campaigns import (
    MAX_ATTEMPTS, cancel_campaign, deliver_member_email, delivery_state, discover_automatic_campaigns,
    queue_campaign, unsubscribe_token,
)
from .models import MemberEmailCampaign, MemberEmailDelivery, MemberEmailSettings, NotificationPreference


@override_settings(
    MEMBER_EMAIL_ENABLED=True, MEMBER_EMAIL_BASE_URL='https://website.example.test',
    MEMBER_EMAIL_POSTAL_ADDRESS='Example community\n123 Example Road', ADMIN_EMAIL_SEND_IMMEDIATELY=False,
)
class MemberCampaignTests(TestCase):
    def setUp(self):
        self.member = self.user('member')
        self.preferences = NotificationPreference.objects.create(user=self.member)

    def user(self, name, **kwargs):
        return get_user_model().objects.create_user(
            email=f'{name}@example.test', username=name, password='Local-Test-Password-742',
            is_active=kwargs.pop('is_active', True), is_verified=kwargs.pop('is_verified', True), **kwargs,
        )

    def opt_in(self, **values):
        values = values or {'email_newsletter': True}
        NotificationPreference.objects.filter(pk=self.preferences.pk).update(**values)

    def campaign(self, **kwargs):
        return MemberEmailCampaign.objects.create(
            subject=kwargs.pop('subject', 'Community news'), body=kwargs.pop('body', 'Hello <script>alert(1)</script>'),
            status=kwargs.pop('status', 'scheduled'), **kwargs,
        )

    def queued(self, **kwargs):
        self.opt_in()
        campaign = self.campaign(**kwargs)
        self.assertEqual(queue_campaign(campaign.pk), 1)
        return campaign, MemberEmailDelivery.objects.get(campaign=campaign)

    def test_default_opt_out_and_verified_active_audience_only(self):
        inactive = self.user('inactive', is_active=False)
        unverified = self.user('unverified', is_verified=False)
        no_preferences = self.user('no_preferences')
        for user in (inactive, unverified):
            NotificationPreference.objects.create(user=user, email_newsletter=True)
        self.assertFalse(self.preferences.email_newsletter)
        self.assertFalse(self.preferences.email_blog_updates)
        self.assertFalse(self.preferences.email_shop_updates)
        self.assertEqual(queue_campaign(self.campaign().pk), 0)
        self.assertFalse(MemberEmailDelivery.objects.exists())
        self.opt_in()
        self.assertEqual(queue_campaign(self.campaign().pk), 1)
        self.assertEqual(MemberEmailDelivery.objects.get().user_id, self.member.pk)

    def test_queue_is_deduplicated_and_content_and_audience_are_frozen(self):
        campaign, row = self.queued()
        later = self.user('later')
        NotificationPreference.objects.create(user=later, email_newsletter=True)
        self.assertEqual(queue_campaign(campaign.pk), 0)
        self.assertEqual(MemberEmailDelivery.objects.count(), 1)
        campaign.refresh_from_db()
        campaign.subject = 'Changed after queue'
        with self.assertRaises(ValidationError):
            campaign.save()
        self.assertTrue(deliver_member_email(row.pk))
        self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.member.email])
        self.assertEqual(message.bcc, [])
        self.assertIn('123 Example Road', message.body)
        self.assertIn('https://website.example.test/account/preferences', message.body)
        self.assertIn('List-Unsubscribe', message.extra_headers)
        self.assertEqual(message.extra_headers['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
        self.assertNotIn('<script>', message.alternatives[0][0])
        self.assertIn('&lt;script&gt;', message.alternatives[0][0])
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'completed')

    def test_queue_rolls_back_with_transaction(self):
        self.opt_in()
        campaign = self.campaign()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                queue_campaign(campaign.pk)
                raise RuntimeError('roll back')
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'scheduled')
        self.assertFalse(MemberEmailDelivery.objects.exists())

    def test_master_and_topic_opt_out_rechecked_before_send(self):
        for changed_field in ('email_enabled', 'email_newsletter'):
            self.opt_in(email_enabled=True, email_newsletter=True)
            campaign = self.campaign()
            queue_campaign(campaign.pk)
            row = MemberEmailDelivery.objects.get(campaign=campaign)
            self.opt_in(**{changed_field: False})
            self.assertFalse(deliver_member_email(row.pk))
            row.refresh_from_db()
            self.assertEqual(row.status, 'cancelled')
        self.assertEqual(len(mail.outbox), 0)

    def test_changed_email_does_not_receive_old_subscription(self):
        _, row = self.queued()
        self.member.email = 'changed@example.test'
        self.member.save(update_fields=['email'])
        self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_deactivated_user_does_not_receive_queued_mail(self):
        _, row = self.queued()
        self.member.is_active = False
        self.member.save(update_fields=['is_active'])
        self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_future_draft_and_disabled_campaigns_do_not_queue(self):
        self.opt_in()
        self.assertEqual(queue_campaign(self.campaign(status='draft').pk), 0)
        self.assertEqual(queue_campaign(self.campaign(scheduled_at=timezone.now()+timedelta(days=1)).pk), 0)
        with override_settings(MEMBER_EMAIL_ENABLED=False):
            self.assertEqual(queue_campaign(self.campaign().pk), 0)
        self.assertFalse(MemberEmailDelivery.objects.exists())

    def test_global_disable_pauses_existing_queue_without_consuming_attempts(self):
        _, row = self.queued()
        with override_settings(MEMBER_EMAIL_ENABLED=False):
            self.assertFalse(deliver_member_email(row.pk))
            output = StringIO()
            call_command('member_email_tick', stdout=output)
            self.assertIn('disabled', output.getvalue())
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')
        self.assertEqual(row.attempts, 0)

    def test_failure_backoff_max_attempts_and_private_diagnostics(self):
        _, row = self.queued()
        with patch('notifications.campaigns.EmailMultiAlternatives.send', side_effect=OSError('private smtp password')):
            self.assertFalse(deliver_member_email(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed')
        self.assertNotIn('private smtp password', row.last_error)
        self.assertGreater(row.next_attempt_at, timezone.now())
        self.assertFalse(deliver_member_email(row.pk))
        MemberEmailDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now(), attempts=MAX_ATTEMPTS)
        self.assertFalse(deliver_member_email(row.pk))
        MemberEmailDelivery.objects.filter(pk=row.pk).update(attempts=1)
        self.assertTrue(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_claimed_delivery_is_not_automatically_reclaimed(self):
        _, row = self.queued()
        MemberEmailDelivery.objects.filter(pk=row.pk).update(status='sending', updated_at=timezone.now()-timedelta(hours=1))
        self.assertFalse(deliver_member_email(row.pk))
        call_command('member_email_tick', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_completion_error_after_smtp_acceptance_cannot_trigger_duplicate_retry(self):
        campaign, row = self.queued()
        with patch('notifications.campaigns.finish_campaign', side_effect=OSError('database temporarily unavailable')):
            self.assertTrue(deliver_member_email(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'sent')
        self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 1)
        call_command('member_email_tick', stdout=StringIO())
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'completed')
        self.assertEqual(len(mail.outbox), 1)

    def test_a_stale_admin_instance_cannot_overwrite_queued_content_or_status(self):
        self.opt_in()
        stale = self.campaign()
        queue_campaign(stale.pk)
        stale.body = 'A different message'
        with self.assertRaises(ValidationError):
            stale.save()
        stale.refresh_from_db()
        self.assertEqual(stale.status, 'queued')
        self.assertNotEqual(stale.body, 'A different message')

    def test_campaign_cancel_prevents_queued_delivery(self):
        campaign, row = self.queued()
        self.assertEqual(cancel_campaign(campaign.pk), 1)
        self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_cancelled_draft_cannot_be_reopened(self):
        campaign = self.campaign(status='draft')
        cancel_campaign(campaign.pk)
        campaign.refresh_from_db()
        campaign.status = 'scheduled'
        with self.assertRaises(ValidationError):
            campaign.save()

    def test_unsubscribe_get_is_read_only_and_post_requires_csrf(self):
        _, row = self.queued()
        client = Client(enforce_csrf_checks=True)
        url = reverse('member_email:unsubscribe', args=[unsubscribe_token(self.member)])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.preferences.refresh_from_db()
        self.assertTrue(self.preferences.email_newsletter)
        self.assertEqual(client.post(url).status_code, 403)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(url, {'csrfmiddlewaretoken': token}).status_code, 200)
        self.preferences.refresh_from_db()
        self.assertFalse(self.preferences.email_newsletter)
        self.assertTrue(self.preferences.email_enabled)
        row.refresh_from_db()
        self.assertEqual(row.status, 'cancelled')

    def test_one_click_signed_post_only_no_login_or_csrf_and_idempotent(self):
        self.opt_in(email_newsletter=True, email_blog_updates=True, email_shop_updates=True)
        client = Client(enforce_csrf_checks=True)
        url = reverse('member_email:one_click', args=[unsubscribe_token(self.member)])
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url).status_code, 400)
        self.assertEqual(client.post(url, {'List-Unsubscribe': 'One-Click'}).status_code, 200)
        self.assertEqual(client.post(url, {'List-Unsubscribe': 'One-Click'}).status_code, 200)
        self.preferences.refresh_from_db()
        self.assertFalse(self.preferences.email_newsletter or self.preferences.email_blog_updates or self.preferences.email_shop_updates)

    def test_invalid_and_address_changed_unsubscribe_tokens_rejected(self):
        self.opt_in()
        token = unsubscribe_token(self.member)
        changed = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        self.assertEqual(self.client.post(reverse('member_email:one_click', args=[changed]), {'List-Unsubscribe': 'One-Click'}).status_code, 400)
        self.member.email = 'new@example.test'
        self.member.save(update_fields=['email'])
        self.assertEqual(self.client.post(reverse('member_email:one_click', args=[token]), {'List-Unsubscribe': 'One-Click'}).status_code, 400)
        self.preferences.refresh_from_db()
        self.assertTrue(self.preferences.email_newsletter)

    def test_preferences_api_accepts_campaign_topics_and_does_not_change_other_fields(self):
        self.client.force_login(self.member)
        url = reverse('platform_api:notification-preferences')
        response = self.client.patch(url, {'email_newsletter': True}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['preferences']['email_newsletter'])
        self.assertFalse(response.json()['preferences']['email_blog_updates'])
        self.assertTrue(response.json()['email_campaign_delivery_active'])
        self.assertFalse(response.json()['email_delivery_active'])
        self.assertEqual(self.client.patch(url, {'email_newsletter': 'true'}, content_type='application/json').status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.patch(url, {'email_newsletter': False}, content_type='application/json').status_code, 401)

    def test_preferences_opt_out_cancels_exhausted_retries_and_does_not_revive_on_opt_in(self):
        campaign, row = self.queued()
        MemberEmailDelivery.objects.filter(pk=row.pk).update(status='failed', attempts=MAX_ATTEMPTS)
        self.client.force_login(self.member)
        url = reverse('platform_api:notification-preferences')
        self.assertEqual(self.client.patch(url, {'email_newsletter': False}, content_type='application/json').status_code, 200)
        campaign.refresh_from_db()
        row.refresh_from_db()
        self.assertEqual(campaign.status, 'completed')
        self.assertEqual(row.status, 'cancelled')
        self.assertEqual(self.client.patch(url, {'email_newsletter': True}, content_type='application/json').status_code, 200)
        self.assertFalse(deliver_member_email(row.pk))

    def test_local_file_capture_marked_captured_and_invalid_backends_blocked(self):
        _, row = self.queued()
        with TemporaryDirectory() as directory:
            with override_settings(EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend', EMAIL_FILE_PATH=directory, V2_LOCAL_PREVIEW=True):
                self.assertTrue(delivery_state()['email_campaign_capture_mode'])
                self.assertFalse(delivery_state()['email_campaign_delivery_active'])
                self.assertTrue(deliver_member_email(row.pk))
            row.refresh_from_db()
            self.assertEqual(row.status, 'captured')
            self.assertEqual(len(list(Path(directory).glob('*.log'))), 1)
        for backend in ('console', 'dummy', 'filebased'):
            _, blocked = self.queued()
            with override_settings(EMAIL_BACKEND=f'django.core.mail.backends.{backend}.EmailBackend', V2_LOCAL_PREVIEW=False):
                self.assertFalse(deliver_member_email(blocked.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_postal_address_and_insecure_origin_block_send(self):
        _, row = self.queued()
        with override_settings(MEMBER_EMAIL_POSTAL_ADDRESS=''):
            self.assertFalse(deliver_member_email(row.pk))
        MemberEmailDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
        with override_settings(MEMBER_EMAIL_BASE_URL='http://example.test', V2_LOCAL_PREVIEW=False):
            self.assertFalse(deliver_member_email(row.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_command_batch_limit_and_queue_only(self):
        self.opt_in()
        self.campaign()
        self.campaign()
        call_command('member_email_tick', limit=2, queue_only=True, stdout=StringIO())
        self.assertEqual(MemberEmailDelivery.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)
        call_command('member_email_tick', limit=1, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        call_command('member_email_tick', limit=1, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)

    def product(self, name, **kwargs):
        # No media bytes are needed: the campaign only reads existing catalog metadata.
        product = Product(name=name, description='Description', thumbnail='test.jpg', main_image='test.jpg',
                          original_price='9.00', redirect_url='https://example.test/product', **kwargs)
        Product.objects.bulk_create([product])
        return product

    def test_automatic_publications_no_backfill_deduplicate_and_skip_amazon(self):
        old = BlogPost.objects.create(title='Old', slug='old', body='Old', status='published', published_at=timezone.now()-timedelta(days=1))
        old_product = self.product('Old product')
        Product.objects.filter(pk=old_product.pk).update(created_at=timezone.now()-timedelta(days=1))
        with patch('notifications.models.timezone.now', return_value=timezone.now()-timedelta(hours=1)):
            config = MemberEmailSettings.objects.create(automatic_blog=True, automatic_shop=True)
        post = BlogPost.objects.create(title='New article', slug='new', body='Text', excerpt='Article excerpt', status='published')
        BlogPost.objects.create(title='Draft', slug='draft', body='Text')
        BlogPost.objects.create(title='Future', slug='future', body='Text', status='published', published_at=timezone.now()+timedelta(days=1))
        product = self.product('New product')
        self.product('Amazon listing', ecommerce_platform='amazon')
        self.product('Inactive listing', is_active=False)
        self.assertEqual(discover_automatic_campaigns(), 2)
        self.assertEqual(discover_automatic_campaigns(), 0)
        self.assertEqual(set(MemberEmailCampaign.objects.values_list('source_key', flat=True)), {f'blog:{post.pk}', f'shop:{product.pk}'})
        self.assertNotIn('Old', '\n'.join(MemberEmailCampaign.objects.values_list('subject', flat=True)))

    def test_reenable_resets_automatic_cutoff(self):
        config = MemberEmailSettings.objects.create(automatic_blog=True)
        previous = config.blog_enabled_since
        config.automatic_blog = False
        config.save()
        BlogPost.objects.create(title='While paused', slug='paused', body='Text', status='published')
        config.automatic_blog = True
        with patch('notifications.models.timezone.now', return_value=timezone.now()+timedelta(seconds=1)):
            config.save()
        self.assertGreater(config.blog_enabled_since, previous)
        self.assertEqual(discover_automatic_campaigns(), 0)

    def test_unpublished_automatic_source_is_cancelled_before_delivery(self):
        self.opt_in(email_blog_updates=True)
        config = MemberEmailSettings.objects.create(automatic_blog=True)
        post = BlogPost.objects.create(title='New article', slug='new', body='Text', status='published')
        discover_automatic_campaigns()
        campaign = MemberEmailCampaign.objects.get()
        queue_campaign(campaign.pk)
        BlogPost.objects.filter(pk=post.pk).update(status='draft')
        row = MemberEmailDelivery.objects.get()
        self.assertFalse(deliver_member_email(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, 'cancelled')

    def test_non_owner_admin_cannot_access_campaigns_or_recipients(self):
        self.member.is_staff = True
        self.member.save(update_fields=['is_staff'])
        self.client.force_login(self.member)
        for model in ('memberemailcampaign', 'memberemaildelivery', 'memberemailsettings'):
            self.assertEqual(self.client.get(f'/admin/notifications/{model}/').status_code, 403)

    def test_manual_interrupted_recovery_does_not_reset_live_claims(self):
        _, row = self.queued()
        self.member.is_superuser = True
        model_admin = admin.site._registry[MemberEmailDelivery]
        request = SimpleNamespace(user=self.member)
        MemberEmailDelivery.objects.filter(pk=row.pk).update(status='sending')
        with patch.object(model_admin, 'message_user'):
            model_admin.retry_interrupted(request, MemberEmailDelivery.objects.all())
            row.refresh_from_db()
            self.assertEqual(row.status, 'sending')
            MemberEmailDelivery.objects.filter(pk=row.pk).update(updated_at=timezone.now()-timedelta(minutes=16))
            model_admin.retry_interrupted(request, MemberEmailDelivery.objects.all())
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed')
        self.assertTrue(deliver_member_email(row.pk))

    def test_admin_retry_resets_exhausted_attempts_but_preserves_cancelled_deliveries(self):
        campaign, row = self.queued()
        MemberEmailDelivery.objects.filter(pk=row.pk).update(status='failed', attempts=MAX_ATTEMPTS)
        self.member.is_superuser = True
        model_admin = admin.site._registry[MemberEmailDelivery]
        request = SimpleNamespace(user=self.member)
        with patch.object(model_admin, 'message_user'):
            model_admin.retry_failed(request, MemberEmailDelivery.objects.all())
        row.refresh_from_db()
        self.assertEqual(row.attempts, 0)
        cancel_campaign(campaign.pk)
        with patch.object(model_admin, 'message_user'):
            model_admin.retry_failed(request, MemberEmailDelivery.objects.all())
        self.assertFalse(deliver_member_email(row.pk))

    def test_subject_header_injection_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.campaign(subject='Hello\r\nBcc: injected@example.test')
