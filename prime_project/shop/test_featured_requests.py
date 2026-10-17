from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import FeaturedShopRequest


class FeaturedRequestTests(TestCase):
    endpoint = '/api/v2/shop/featured-requests/'

    def setUp(self):
        FeaturedShopRequest.objects.all().delete()

    def test_public_order_visibility_and_placeholder_link(self):
        FeaturedShopRequest.objects.create(title='Hidden', description='Hidden', is_active=False)
        later = FeaturedShopRequest.objects.create(title='Media', description='Media', sort_order=20)
        first = FeaturedShopRequest.objects.create(
            title='Edit', description='Edit', sort_order=10,
            purchase_url='https://buymeacoffee.com/example/e/123',
        )
        response = self.client.get(self.endpoint + '?search=unrelated&category=other&page=99')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['Cache-Control'])
        records = response.json()['results']
        self.assertEqual([item['id'] for item in records], [first.pk, later.pk])
        self.assertEqual(records[0]['purchase_url'], '')
        self.assertTrue(records[0]['is_placeholder'])
        FeaturedShopRequest.objects.all().update(is_active=False)
        self.assertEqual(self.client.get(self.endpoint).json()['results'], [])

    def test_live_request_requires_valid_provider_link(self):
        request = FeaturedShopRequest(title='Edit', description='Custom edit', is_placeholder=False)
        for url in ['', 'http://buymeacoffee.com/example', 'https://buymeacoffee.com.evil.test/a',
                    'https://user@buymeacoffee.com/a', 'https://buymeacoffee.com:444/a',
                    'javascript:alert(1)']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                request.purchase_url = url
                request.save()
        request.purchase_url = 'https://buymeacoffee.com/example/e/123'
        request.save()
        self.assertEqual(self.client.get(self.endpoint).json()['results'][0]['purchase_url'], request.purchase_url)

    def test_admin_edits_are_public_and_admin_requires_login(self):
        item = FeaturedShopRequest.objects.create(title='Edit', description='Old copy')
        url = f'/admin/shop/featuredshoprequest/{item.pk}/change/'
        self.assertEqual(self.client.get(url).status_code, 302)
        admin = get_user_model().objects.create_superuser(
            email='request-admin@example.test', username='requestadmin', password='test',
        )
        self.client.force_login(admin)
        self.assertContains(self.client.get(url), 'placeholder mode')
        response = self.client.post(url, {
            'title': 'Custom Edit Request', 'description': 'Updated by the owner',
            'details': 'Send a reference link.', 'icon': 'edit', 'badge': 'Featured',
            'price_label': 'From $25', 'turnaround': '5 days',
            'button_label': 'Request an edit', 'placeholder_label': 'Coming soon',
            'purchase_url': 'https://buymeacoffee.com/example/e/123',
            'is_active': 'on', 'sort_order': 5, '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        record = self.client.get(self.endpoint).json()['results'][0]
        self.assertEqual(record['title'], 'Custom Edit Request')
        self.assertEqual(record['description'], 'Updated by the owner')
        self.assertEqual(record['price_label'], 'From $25')
        self.assertFalse(record['is_placeholder'])

    def test_public_api_is_read_only(self):
        self.assertEqual(self.client.post(self.endpoint, {}).status_code, 405)
