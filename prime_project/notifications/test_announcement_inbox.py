from django.contrib.auth import get_user_model
from django.test import TestCase

from announcements.models import Announcement
from .models import Notification, NotificationPreference, MemberActivityDelivery


class AnnouncementInboxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='reader', email='reader@example.test', password='test', is_verified=True)
        self.other = get_user_model().objects.create_user(username='other', email='other@example.test', password='test', is_verified=True)
        self.client.force_login(self.user)

    def test_existing_announcement_becomes_title_only_unread_and_stays_read(self):
        item = Announcement.objects.create(title='Community news', message='<p>Full content</p>')
        response = self.client.get('/api/v2/notifications/').json()
        notice = response['results'][0]
        self.assertEqual(response['unread_count'], 1)
        self.assertEqual(notice['title'], item.title)
        self.assertEqual(notice['message'], '')
        self.assertEqual(notice['url'], f'/community-updates?announcement={item.pk}')
        self.client.post(f"/api/v2/notifications/{notice['id']}/read/")
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['unread_count'], 0)
        item.title = 'Updated title'
        item.save()
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['results'][0]['title'], item.title)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(MemberActivityDelivery.objects.count(), 0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['unread_count'], 1)

    def test_inactive_and_opted_out_are_hidden_detail_is_filtered(self):
        item = Announcement.objects.create(title='News', message='Body')
        self.client.get('/api/v2/notifications/')
        NotificationPreference.objects.create(user=self.user, in_app_enabled=False)
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['count'], 0)
        item.is_active = False
        item.save()
        NotificationPreference.objects.filter(user=self.user).update(in_app_enabled=True)
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['count'], 0)
        self.assertEqual(self.client.get(f'/api/v2/announcements/?announcement={item.pk}').json()['count'], 0)

    def test_deep_link_finds_older_announcement_and_mark_all(self):
        first = Announcement.objects.create(title='First', message='Full body')
        Announcement.objects.create(title='Second', message='Other')
        result = self.client.get(f'/api/v2/announcements/?announcement={first.pk}').json()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['message'], 'Full body')
        self.client.post('/api/v2/notifications/read-all/')
        self.assertEqual(self.client.get('/api/v2/notifications/').json()['unread_count'], 0)
