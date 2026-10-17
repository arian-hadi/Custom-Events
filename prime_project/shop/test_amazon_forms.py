from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from .amazon_forms import AmazonSourceForm, product_identity
from .amazon_models import AmazonSource


class ProductLinkTests(SimpleTestCase):
    def test_full_product_links(self):
        for url, market in [
            ('https://www.amazon.com/Figure-Name/dp/B0199980K4/ref=abc?tag=other-20', 'www.amazon.com'),
            ('https://amazon.co.uk/gp/product/B0199980K4?ref=share', 'www.amazon.co.uk'),
            ('https://m.amazon.de/gp/aw/d/B0199980K4/', 'www.amazon.de'),
            ('www.amazon.com.tr/dp/b0199980k4', 'www.amazon.com.tr'),
        ]:
            self.assertEqual(product_identity(url), ('B0199980K4', market))

    def test_invalid_hosts_and_non_product_links(self):
        for url in ['https://amazon.com.evil.test/dp/B0199980K4',
                    'https://user@amazon.com/dp/B0199980K4', 'https://amazon.com:443/dp/B0199980K4',
                    'https://example.test/dp/B0199980K4', 'https://amazon.com/s?k=figure',
                    'https://amazon.com/dp/B0199980K4EXTRA', 'https://amzn.to/example',
                    'https://a.co/example', 'https://amazon.com:bad/dp/B0199980K4']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                product_identity(url)


@override_settings(AMAZON_MARKETPLACE='www.amazon.com')
class AmazonSourceFormTests(TestCase):
    def test_url_only_extracts_identity_and_duplicate_is_rejected(self):
        data = {'product_url': 'https://www.amazon.co.uk/dp/B0199980K4?tag=other',
                'marketplace': 'www.amazon.com', 'enabled': 'on'}
        form = AmazonSourceForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        source = form.save()
        self.assertEqual((source.asin, source.marketplace), ('B0199980K4', 'www.amazon.co.uk'))
        self.assertFalse(source.publish)
        self.assertFalse(AmazonSourceForm(data).is_valid())

    def test_manual_and_conflicting_input(self):
        form = AmazonSourceForm({'asin': 'b0199980k4', 'marketplace': 'www.amazon.com'})
        self.assertTrue(form.is_valid(), form.errors)
        for data in [{}, {'product_url': 'https://amazon.com/dp/B0199980K4', 'asin': 'B000000000'}]:
            self.assertFalse(AmazonSourceForm(data).is_valid())

    def test_admin_add_by_link_and_change_preserves_identity(self):
        user = get_user_model().objects.create_superuser(email='admin@example.test', username='admin', password='test')
        self.client.force_login(user)
        url = '/admin/shop/amazonsource/add/'
        self.assertContains(self.client.get(url), 'Amazon product link')
        response = self.client.post(url, {'product_url': 'https://amazon.com/dp/B0199980K4',
            'marketplace': 'www.amazon.com', 'enabled': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        source = AmazonSource.objects.get()
        change = f'/admin/shop/amazonsource/{source.pk}/change/'
        self.assertNotContains(self.client.get(change), 'name="product_url"')
        response = self.client.post(change, {'enabled': 'on', 'publish': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        self.assertTrue(source.publish)
        self.assertEqual(source.asin, 'B0199980K4')
