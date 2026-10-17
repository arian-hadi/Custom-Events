from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.forms import modelform_factory
from django.contrib import admin as django_admin
from django.test import Client, RequestFactory, TestCase, override_settings

from accounts.middleware import V2EditorApplicationRedirectMiddleware
from edithub.models import EditorApplication
from edithub.admin import EditorApplicationAdmin
from edithub.forms import EditorApplicationAdminForm
from notifications.models import AdminEmailDelivery


@override_settings(ADMIN_NOTIFICATION_RECIPIENTS='admin@example.test', ADMIN_EMAIL_SEND_IMMEDIATELY=False)
class EditorApplicationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email='creator@example.test', username='creator', password='test', is_verified=True)
        cls.other = User.objects.create_user(email='other@example.test', username='other', password='test', is_verified=True)
        cls.admin = User.objects.create_user(email='admin@example.test', username='admin', password='test', role='admin', is_staff=True, is_verified=True)

    def setUp(self):
        cache.clear()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.member)
        self.lookup = patch('platform_api.editor_views.fetch_youtube_channel_data', return_value={
            'channel_name': 'Example creator', 'subscriber_count': 12345, 'thumbnail': '',
        }).start()
        self.addCleanup(patch.stopall)

    def upload(self, **changes):
        content = BytesIO()
        Image.new('RGB', (8, 8)).save(content, format='PNG')
        data = {'channel_type': 'youtube', 'channel_link': 'https://www.youtube.com/@creator',
                'editing_area': 'transformers', 'editing_tool': 'after_effects', 'data_consent': 'on',
                'channel_screenshot': SimpleUploadedFile('channel.png', content.getvalue(), 'image/png')}
        data.update(changes)
        return self.client.post('/api/v2/editor-applications/', data)

    def action(self, pk, name, data=None):
        return self.client.post(f'/api/v2/editor-applications/{pk}/{name}/', data or {}, content_type='application/json')

    def test_draft_confirmation_and_admin_alert_are_separate_and_idempotent(self):
        response = self.upload(channel_verified='on', status='accepted', user=self.other.pk)
        self.assertEqual(response.status_code, 201, response.content)
        item = EditorApplication.objects.get()
        self.assertEqual(item.user, self.member)
        self.assertEqual(item.status, 'pending')
        self.assertFalse(item.channel_verified)
        self.assertEqual(AdminEmailDelivery.objects.count(), 0)
        self.assertNotIn('follower_count', response.json()['application'])
        self.assertNotIn('rank_position', response.json()['application'])
        self.assertEqual(self.action(item.pk, 'confirm').status_code, 400)
        for _ in range(2):
            self.assertEqual(self.action(item.pk, 'confirm', {'owns_channel': True}).status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.channel_verified)
        self.assertEqual(AdminEmailDelivery.objects.filter(kind='editor_application', status='pending').count(), 1)

    def test_missing_consent_invalid_image_and_other_area_are_rejected_before_lookup(self):
        for changes in ({'data_consent': ''}, {'editing_area': 'others'},
                        {'channel_screenshot': SimpleUploadedFile('invalid.png', b'not an image', 'image/png')}):
            self.assertEqual(self.upload(**changes).status_code, 400)
        self.lookup.assert_not_called()
        self.assertEqual(EditorApplication.objects.count(), 0)

    def test_wrong_platform_spoofed_host_and_video_urls_are_rejected(self):
        for link in ('https://youtube.com.evil.test/@creator', 'https://example.test/youtube.com/@creator',
                     'https://www.youtube.com/watch?v=example', 'https://www.tiktok.com/@creator',
                     'https://user@www.youtube.com/@creator', 'https://www.youtube.com:999/@creator'):
            self.assertEqual(self.upload(channel_link=link).status_code, 400, link)
        self.lookup.assert_not_called()

    def test_duplicate_cannot_create_more_files_or_lookup_again(self):
        first = self.upload()
        self.assertEqual(first.status_code, 201)
        second = self.upload(channel_link='https://www.youtube.com/@another')
        self.assertEqual(second.status_code, 409)
        self.assertEqual(EditorApplication.objects.count(), 1)
        self.assertEqual(self.lookup.call_count, 1)

    def test_one_active_application_across_both_platforms(self):
        first = self.upload().json()['application']['id']
        with patch('platform_api.editor_views.fetch_tiktok_channel_data') as tiktok:
            for status in ('pending', 'accepted'):
                EditorApplication.objects.filter(pk=first).update(status=status)
                response = self.upload(channel_type='tiktok', channel_link='https://www.tiktok.com/@creator')
                self.assertEqual(response.status_code, 409, response.content)
                self.assertEqual(response.json()['application']['id'], first)
            tiktok.assert_not_called()
        self.assertEqual(EditorApplication.objects.count(), 1)

    def test_inactive_history_allows_choosing_a_different_platform(self):
        first = self.upload().json()['application']['id']
        EditorApplication.objects.filter(pk=first).update(status='rejected')
        with patch('platform_api.editor_views.fetch_tiktok_channel_data', return_value={'channel_name': 'TikTok creator'}):
            response = self.upload(channel_type='tiktok', channel_link='https://www.tiktok.com/@creator')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(EditorApplication.objects.count(), 2)
        self.assertEqual(EditorApplication.objects.get(pk=first).status, 'rejected')

    def test_concurrent_application_is_rechecked_after_provider_lookup(self):
        def creates_other_application(_):
            EditorApplication.objects.bulk_create([EditorApplication(
                user=self.member, channel_type='tiktok', channel_link='https://www.tiktok.com/@creator',
                editing_area='transformers', status='pending')])
            return {'channel_name': 'YouTube creator'}
        self.lookup.side_effect = creates_other_application
        response = self.upload()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['application']['platform'], 'tiktok')
        self.assertEqual(EditorApplication.objects.count(), 1)

    def test_historical_dual_platform_records_are_preserved_and_visible(self):
        first = self.upload().json()['application']['id']
        second = EditorApplication(user=self.member, channel_type='tiktok',
            channel_link='https://www.tiktok.com/@creator', editing_area='transformers', status='accepted')
        EditorApplication.objects.bulk_create([second])
        self.assertEqual(self.upload(channel_link='https://www.youtube.com/@different').status_code, 409)
        data = self.client.get('/api/v2/member/dashboard/').json()
        self.assertEqual({item['id'] for item in data['applications']['editors']}, {first, second.pk})
        self.assertEqual(EditorApplication.objects.count(), 2)

    def test_admin_form_prevents_second_active_channel_but_preserves_history(self):
        first = self.upload().json()['application']['id']
        Form = modelform_factory(EditorApplication, form=EditorApplicationAdminForm,
            fields=('user', 'status', 'channel_type', 'channel_link', 'editing_area', 'removal_requested'))
        data = {'user': self.member.pk, 'status': 'pending', 'channel_type': 'tiktok',
                'channel_link': 'https://www.tiktok.com/@creator', 'editing_area': 'transformers'}
        self.assertFalse(Form(data=data).is_valid())
        data['status'] = 'rejected'
        form = Form(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        historical = form.save()
        data['status'] = 'accepted'
        self.assertFalse(Form(data=data, instance=historical).is_valid())
        # Previously active historical duplicates remain editable without deletion.
        EditorApplication.objects.filter(pk=historical.pk).update(status='accepted')
        historical.refresh_from_db()
        self.assertTrue(Form(data=data, instance=historical).is_valid())
        self.assertTrue(EditorApplication.objects.filter(pk=first).exists())

    def test_admin_bulk_and_legacy_status_cannot_reactivate_second_channel(self):
        self.upload()
        old = EditorApplication(user=self.member, channel_type='tiktok',
            channel_link='https://www.tiktok.com/@creator', editing_area='transformers', status='rejected')
        EditorApplication.objects.bulk_create([old])
        self.client.force_login(self.admin)
        response = self.client.post(f'/editinghub/admin/application/{old.pk}/update-status/', {'status': 'accepted'})
        self.assertEqual(response.status_code, 409, response.content)
        model_admin = EditorApplicationAdmin(EditorApplication, django_admin.site)
        request = RequestFactory().post('/admin/edithub/editorapplication/')
        request.user = self.admin
        with patch.object(model_admin, 'message_user'):
            model_admin.accept_applications(request, EditorApplication.objects.filter(pk=old.pk))
        old.refresh_from_db()
        self.assertEqual(old.status, 'rejected')

    def test_legacy_application_post_cannot_add_second_platform(self):
        self.upload()
        content = BytesIO()
        Image.new('RGB', (8, 8)).save(content, format='PNG')
        data = {'platform': 'tiktok', 'data_consent': 'on',
                'tiktok-channel_link': 'https://www.tiktok.com/@creator',
                'tiktok-editing_area': 'transformers', 'tiktok-editing_tool': 'after_effects',
                'tiktok-channel_screenshot': SimpleUploadedFile('proof.png', content.getvalue(), 'image/png')}
        with patch('edithub.views.fetch_tiktok_channel_data') as lookup, patch(
                'edithub.views.render', return_value=HttpResponse('application form')):
            self.client.post('/editinghub/apply/', data)
        lookup.assert_not_called()
        self.assertEqual(EditorApplication.objects.count(), 1)

    def test_provider_errors_do_not_create_application_or_expose_provider_secrets(self):
        self.lookup.return_value = {'error': 'private provider diagnostics'}
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private provider', response.content.decode())
        self.assertEqual(EditorApplication.objects.count(), 0)

    def test_youtube_failure_messages_distinguish_configuration_from_channel(self):
        for code, status, phrase in [
            ('configuration_error', 503, 'not configured correctly'),
            ('quota_exceeded', 503, 'limit has been reached'),
            ('channel_not_found', 400, 'could not find this channel'),
        ]:
            self.lookup.return_value = {'error': 'private details', 'error_code': code}
            response = self.upload()
            self.assertEqual(response.status_code, status)
            self.assertContains(response, phrase, status_code=status)
            self.assertEqual(response.json()['code'], code)
        self.assertEqual(EditorApplication.objects.count(), 0)

    def test_tiktok_uses_existing_provider_and_preserves_partial_channel_lookup(self):
        with patch('platform_api.editor_views.fetch_tiktok_channel_data', return_value={'channel_name': 'TikTok creator', 'error': 'stats unavailable'}):
            response = self.upload(channel_type='tiktok', channel_link='https://www.tiktok.com/@creator')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['application']['platform'], 'tiktok')
        self.assertFalse(response.json()['application']['channel_verified'])

    def test_owner_only_reads_and_mutations(self):
        pk = self.upload().json()['application']['id']
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v2/editor-applications/').json()['results'], [])
        self.assertEqual(self.client.get(f'/api/v2/editor-applications/{pk}/').status_code, 404)
        for action in ('confirm', 'cancel', 'remove'):
            self.assertEqual(self.action(pk, action, {'owns_channel': True}).status_code, 404)

    def test_auth_roles_csrf_and_post_only_mutations(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/v2/editor-applications/').status_code, 401)
        self.client.force_login(self.admin)
        self.assertFalse(self.client.get('/api/v2/editor-applications/').json()['can_apply'])
        self.assertEqual(self.upload().status_code, 403)
        self.client.force_login(self.member)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.member)
        self.assertEqual(secure.post('/api/v2/editor-applications/').status_code, 403)
        self.assertEqual(self.client.get('/api/v2/editor-applications/1/confirm/').status_code, 405)
        self.member.is_verified = False
        self.member.save(update_fields=['is_verified'])
        self.assertEqual(self.client.get('/api/v2/editor-applications/').status_code, 401)

    def test_cancel_only_unconfirmed_drafts(self):
        pk = self.upload().json()['application']['id']
        self.assertEqual(self.action(pk, 'cancel').status_code, 200)
        self.assertEqual(EditorApplication.objects.count(), 0)
        pk = self.upload().json()['application']['id']
        self.action(pk, 'confirm', {'owns_channel': True})
        self.assertEqual(self.action(pk, 'cancel').status_code, 409)

    def test_approved_removal_alert_is_deduplicated_and_no_member_can_self_approve(self):
        pk = self.upload().json()['application']['id']
        self.assertEqual(self.action(pk, 'remove').status_code, 409)
        # Simulate the separate admin decision without invoking legacy ranking jobs.
        EditorApplication.objects.filter(pk=pk).update(status='accepted', channel_verified=True)
        for _ in range(2):
            self.assertEqual(self.action(pk, 'remove').status_code, 200)
        self.assertEqual(AdminEmailDelivery.objects.filter(kind='editor_removal').count(), 1)
        self.assertEqual(self.action(pk, 'confirm', {'owns_channel': True}).status_code, 409)

    def test_dashboard_editor_links_stay_in_v2(self):
        data = self.client.get('/api/v2/member/dashboard/').json()
        self.assertEqual(data['applications']['editors'], [])
        pk = self.upload().json()['application']['id']
        data = self.client.get('/api/v2/member/dashboard/').json()
        self.assertEqual(data['applications']['editors'][0]['url'], f'/applications/editors/{pk}')
        self.assertEqual(len(data['applications']['editors']), 1)

    def test_approved_before_confirmation_can_finish_without_reapplying(self):
        pk = self.upload().json()['application']['id']
        EditorApplication.objects.filter(pk=pk).update(status='accepted')
        detail = self.client.get(f'/api/v2/editor-applications/{pk}/').json()['application']
        self.assertTrue(detail['can_confirm'])
        own = self.client.get('/api/v2/league/entries/me/').json()
        self.assertEqual(own['verified_channels'], [])
        self.assertEqual(own['channel_applications'][0]['url'], f'/applications/editors/{pk}')
        self.assertEqual(own['channel_applications'][0]['status'], 'accepted')
        self.assertEqual(self.action(pk, 'confirm').status_code, 400)
        for _ in range(2):
            self.assertEqual(self.action(pk, 'confirm', {'owns_channel': True}).status_code, 200)
        item = EditorApplication.objects.get(pk=pk)
        self.assertEqual(item.status, 'accepted')
        self.assertTrue(item.channel_verified)
        own = self.client.get('/api/v2/league/entries/me/').json()
        self.assertEqual([channel['id'] for channel in own['verified_channels']], [pk])
        self.assertEqual(EditorApplication.objects.count(), 1)
        self.assertEqual(AdminEmailDelivery.objects.filter(kind='editor_application').count(), 0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v2/league/entries/me/').json()['channel_applications'], [])
        self.assertEqual(self.action(pk, 'confirm', {'owns_channel': True}).status_code, 404)

    def test_approved_confirmation_still_requires_evidence_and_respects_removal(self):
        pk = self.upload().json()['application']['id']
        for values in ({'status': 'accepted', 'data_consent': False},
                       {'data_consent': True, 'channel_screenshot': ''},
                       {'channel_screenshot': 'fixture.png', 'removal_requested': True},
                       {'removal_requested': False, 'status': 'rejected'}):
            EditorApplication.objects.filter(pk=pk).update(**values)
            self.assertEqual(self.action(pk, 'confirm', {'owns_channel': True}).status_code, 409)
            self.assertFalse(EditorApplication.objects.get(pk=pk).channel_verified)


class EditorLegacyRedirectTests(TestCase):
    def response(self, path, post=False):
        request = (RequestFactory().post if post else RequestFactory().get)(path)
        return V2EditorApplicationRedirectMiddleware(lambda _: HttpResponse('legacy'))(request)

    @override_settings(V2_TRUST_GATEWAY_ADDRESS=True, V2_FRONTEND_URL='http://localhost:8082')
    def test_v2_routes_old_links_and_scoped_login_to_new_pages(self):
        cases = {
            '/editinghub/apply/?edit_platform=tiktok': '/editing-hub/apply?platform=tiktok',
            '/editinghub/application/17/': '/applications/editors/17',
            '/editinghub/application/17/remove/': '/applications/editors/17',
            '/editinghub/confirm/': '/applications',
            '/accounts/login/?next=/editinghub/apply/': '/login?next=%2Fediting-hub%2Fapply%3Fplatform%3Dyoutube',
        }
        for path, destination in cases.items():
            self.assertEqual(self.response(path)['Location'], 'http://localhost:8082' + destination)
        self.assertEqual(self.response('/editinghub/apply/', post=True).status_code, 200)
        self.assertEqual(self.response('/accounts/login/?next=https://evil.test/editinghub/apply/').status_code, 200)
        self.assertEqual(self.response('/accounts/login/?next=/admin/').status_code, 200)

    def test_legacy_deployment_keeps_existing_pages(self):
        self.assertEqual(self.response('/editinghub/apply/').status_code, 200)
