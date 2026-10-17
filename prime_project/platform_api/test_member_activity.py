from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.middleware import V2EditorApplicationRedirectMiddleware
from edithub.models import EditSubmission, EditorApplication
from events.models import Event, EventApplication, EventField, EventFieldResponse


@override_settings(ADMIN_EMAIL_SEND_IMMEDIATELY=False, MEMBER_ACTIVITY_EMAIL_ENABLED=False)
class MemberActivityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='member@example.test', username='member', password='password123', is_verified=True)
        self.other = User.objects.create_user(email='other@example.test', username='other', password='password123', is_verified=True)
        self.client.force_login(self.user)
        self.event = Event.objects.create(title='Community edit', created_by=self.other, description='Join us',
            deadline=timezone.now() + timedelta(days=3), date=timezone.now() + timedelta(days=5))
        self.number = EventField.objects.create(event=self.event, name='Number', field_type='number')
        self.boolean = EventField.objects.create(event=self.event, name='Permission', field_type='boolean')
        self.application = EventApplication.objects.create(event=self.event, applicant=self.user)
        self.path = f'/api/v2/applications/{self.application.pk}/'

    def test_event_update_keeps_false_zero_and_does_not_change_owner_or_status(self):
        response = self.client.post(self.path, {'cover_letter': 'Updated', f'field_{self.number.pk}': 0,
            f'field_{self.boolean.pk}': False, 'status': 'accepted', 'applicant': self.other.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.application.refresh_from_db()
        self.assertEqual((self.application.status, self.application.applicant_id), ('pending', self.user.pk))
        self.assertEqual(EventFieldResponse.objects.get(field=self.number).value_number, 0)
        self.assertFalse(EventFieldResponse.objects.get(field=self.boolean).value_boolean)
        data = response.json()['application']
        self.assertEqual(data['url'], f'/applications/events/{self.application.pk}')
        self.assertNotIn('legacy_url', data)

    def test_event_owner_and_csrf_are_required(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.path, {}, content_type='application/json').status_code, 403)

    def test_reviewed_closed_and_inactive_applications_cannot_be_changed(self):
        for status, active, deadline in [('reviewing', True, 1), ('accepted', True, 1), ('pending', False, 1), ('pending', True, -1)]:
            EventApplication.objects.filter(pk=self.application.pk).update(status=status)
            Event.objects.filter(pk=self.event.pk).update(is_active=active, deadline=timezone.now() + timedelta(days=deadline))
            self.assertEqual(self.client.post(self.path, {}, content_type='application/json').status_code, 409)
            self.assertFalse(self.client.get(self.path).json()['application']['can_edit'])

    def test_invalid_event_answers_do_not_partially_update(self):
        response = self.client.post(self.path, {'cover_letter': 'unsaved', f'field_{self.number.pk}': 'invalid'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.application.refresh_from_db()
        self.assertEqual(self.application.cover_letter, '')
        self.assertFalse(EventFieldResponse.objects.exists())

    def edit(self, days=5):
        channel = EditorApplication.objects.create(user=self.user, channel_type='youtube', channel_link='https://www.youtube.com/@member',
            channel_name='Member', editing_area='transformers', editing_tool='after_effects', status='accepted', channel_verified=True)
        return EditSubmission.objects.create(user=self.user, approved_application=channel, channel_type='youtube',
            video_url='https://www.youtube.com/watch?v=AbCdEfGhI_1', title='Old edit', scheduled_week=(timezone.now() + timedelta(days=days)).date())

    def test_earlier_edit_ownership_locked_history_and_no_legacy_ranks(self):
        edit = self.edit(-5)
        url = f'/api/v2/member/edits/{edit.pk}/'
        data = self.client.get(url).json()['edit']
        self.assertFalse(data['can_edit'])
        self.assertNotIn('week_rank', data)
        self.assertNotIn('calculated_points', data)
        self.assertEqual(self.client.post(url, {'operation': 'withdraw'}, content_type='application/json').status_code, 409)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_earlier_draft_save_and_confirmation_ignore_privileged_fields(self):
        edit = self.edit()
        url = f'/api/v2/member/edits/{edit.pk}/'
        response = self.client.post(url, {'title': 'Changed', 'status': 'verified', 'calculated_points': 9000}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        edit.refresh_from_db()
        self.assertEqual(edit.status, 'pending')
        self.assertEqual(edit.title, 'Changed')
        self.assertEqual(self.client.post(url, {'operation': 'confirm'}, content_type='application/json').status_code, 400)
        response = self.client.post(url, {'operation': 'confirm', 'owns_edit': True}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        edit.refresh_from_db()
        self.assertEqual(edit.status, 'verified')

    @patch('platform_api.activity_views.fetch_verified_video', side_effect=ValueError('wrong owner'))
    def test_replacement_video_requires_server_verification(self, fetch):
        edit = self.edit()
        response = self.client.post(f'/api/v2/member/edits/{edit.pk}/', {'video_url': 'https://www.youtube.com/watch?v=Different_1'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        edit.refresh_from_db()
        self.assertTrue(edit.video_url.endswith('AbCdEfGhI_1'))


@override_settings(V2_LOCAL_PREVIEW=True, V2_FRONTEND_URL='http://localhost:8082')
class V2MemberRedirectTests(TestCase):
    def test_bookmarks_use_v2_and_posts_and_admin_remain_backend_owned(self):
        middleware = V2EditorApplicationRedirectMiddleware(lambda request: HttpResponse('backend'))
        factory = RequestFactory()
        mappings = {'/accounts/profile/': '/account/profile', '/editinghub/customize-profile/': '/account/profile',
            '/dashboard/user/': '/account', '/dashboard/application/12/edit/': '/applications/events/12',
            '/editinghub/edit-submission/9/preview/': '/account/edits/9', '/editinghub/edits/': '/account/edits'}
        for old, new in mappings.items():
            self.assertEqual(middleware(factory.get(old))['Location'], 'http://localhost:8082' + new)
            self.assertEqual(middleware(factory.post(old)).status_code, 200)
        self.assertEqual(middleware(factory.get('/accounts/login/?next=/admin/')).status_code, 200)
        self.assertTrue(middleware(factory.get('/accounts/login/?next=/dashboard/user/'))['Location'].startswith('http://localhost:8082/login?'))

