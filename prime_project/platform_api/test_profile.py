from io import BytesIO
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from edithub.models import EditorApplication, EditorTitle, UserTitleUnlock
from shop.models import PaymentOrder, Product


URL = '/api/v2/member/profile/'


class MemberProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(email='profile@example.test', username='ProfileMember', password='Testing-123!', is_verified=True)
        cls.other = get_user_model().objects.create_user(email='other-profile@example.test', username='OtherProfile', password='Testing-123!', is_verified=True)

    def setUp(self):
        cache.clear()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.member)

    def change(self, **data):
        return self.client.post(URL, data, content_type='application/json')

    def application(self, user=None, platform='youtube', **values):
        fields = {'user': user or self.member, 'channel_type': platform, 'channel_link': f'https://example.test/{uuid4()}',
                  'editing_area': 'transformers', 'status': 'accepted', 'channel_verified': True, 'channel_name': f'{platform} creator',
                  'channel_thumbnail': f'https://example.test/{platform}.png'}
        fields.update(values)
        record = EditorApplication(**fields)
        EditorApplication.objects.bulk_create([record])
        return record

    def image(self, size=(12, 12), kind='PNG'):
        content = BytesIO()
        Image.new('RGB', size, 'red').save(content, format=kind)
        return SimpleUploadedFile('profile.png', content.getvalue() + b'EXTRA_UNTRUSTED_DATA', 'image/png')

    def delete(self, **data):
        return self.client.post(URL + 'delete/', data, content_type='application/json')

    def test_read_is_private_verified_and_uncached(self):
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.client.force_login(self.member)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response.json()['member']['display_name'], 'ProfileMember')
        self.assertEqual(response.json()['channels'], [])
        self.assertEqual(response.json()['titles'], [])
        self.assertTrue(response.json()['deletion']['password_required'])
        for changes in ({'is_verified': False}, {'is_verified': True, 'is_active': False}):
            get_user_model().objects.filter(pk=self.member.pk).update(**changes)
            self.assertEqual(self.client.get(URL).status_code, 401)

    def test_csrf_and_http_methods(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.member)
        self.assertEqual(secure.post(URL, {}, content_type='application/json').status_code, 403)
        self.assertEqual(secure.post(URL + 'delete/', {}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.get(URL + 'delete/').status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)

    def test_only_owned_approved_verified_channels_and_no_follower_ranking(self):
        self.application(user=self.other)
        own = self.application(platform='tiktok', status='pending')
        self.application(channel_verified=False)
        self.application(removal_requested=True)
        self.assertEqual(self.client.get(URL).json()['channels'], [])
        self.assertEqual(self.change(profile_display_mode='channel', approved_channel_source='tiktok').status_code, 400)
        EditorApplication.objects.filter(pk=own.pk).update(status='accepted')
        response = self.change(profile_display_mode='channel', approved_channel_source='tiktok')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['member']['display_name'], 'tiktok creator')
        self.assertEqual(response.json()['member']['profile_picture'], 'https://example.test/tiktok.png')
        self.assertEqual(response.json()['member']['verified_platforms'], ['tiktok'])
        self.assertNotIn('follower_count', str(response.json()))
        self.member.refresh_from_db()
        self.assertEqual(self.member.get_display_name(), 'tiktok creator')

    def test_revoked_channel_falls_back_and_account_mode_can_be_restored(self):
        channel = self.application()
        self.assertEqual(self.change(profile_display_mode='channel', approved_channel_source='youtube').status_code, 200)
        EditorApplication.objects.filter(pk=channel.pk).update(removal_requested=True)
        self.member.refresh_from_db()
        self.assertEqual(self.member.get_display_name(), self.member.username)
        self.assertIsNone(self.member.get_display_picture())
        self.assertEqual(self.change(profile_display_mode='account').status_code, 200)

    def test_channel_source_is_explicit_and_never_selected_by_followers(self):
        self.application(follower_count=1000000)
        self.application(platform='tiktok', follower_count=1)
        self.assertEqual(self.change(profile_display_mode='channel').status_code, 400)
        response = self.change(profile_display_mode='channel', approved_channel_source='tiktok')
        self.assertEqual(response.json()['member']['display_name'], 'tiktok creator')

    def test_profile_image_is_decoded_reencoded_and_removable(self):
        channel = self.application()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(URL, {'profile_picture': self.image(), 'profile_display_mode': 'channel', 'approved_channel_source': channel.channel_type})
        self.assertEqual(response.status_code, 200, response.content)
        self.member.refresh_from_db()
        stored = self.member.profile_picture.name
        storage = self.member.profile_picture.storage
        self.assertTrue(stored.startswith('profile_pictures/'))
        with storage.open(stored, 'rb') as file:
            content = file.read()
        self.assertNotIn(b'EXTRA_UNTRUSTED_DATA', content)
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.format, 'PNG')
        self.assertEqual(response.json()['member']['profile_picture'], response.json()['profile']['uploaded_picture'])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.change(remove_picture=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['profile']['uploaded_picture'])
        self.assertEqual(response.json()['member']['profile_picture'], channel.channel_thumbnail)
        self.assertFalse(storage.exists(stored))

    def test_replacement_removes_old_image_only_after_commit(self):
        self.client.post(URL, {'profile_picture': self.image()})
        self.member.refresh_from_db()
        original = self.member.profile_picture.name
        storage = self.member.profile_picture.storage
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(URL, {'profile_picture': self.image()})
            self.assertTrue(storage.exists(original))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(storage.exists(original))
        self.member.refresh_from_db()
        self.assertTrue(storage.exists(self.member.profile_picture.name))

    def test_invalid_large_and_conflicting_images_rejected_without_profile_mutation(self):
        files = [SimpleUploadedFile('avatar.svg', b'<svg onload="alert(1)"></svg>', 'image/svg+xml'),
                 SimpleUploadedFile('avatar.png', b'not-an-image', 'image/png'), self.image((4097, 1)),
                 SimpleUploadedFile('large.png', b'x' * (5 * 1024 * 1024 + 1), 'image/png')]
        for file in files:
            response = self.client.post(URL, {'profile_picture': file})
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.client.post(URL, {'profile_picture': self.image(), 'remove_picture': 'true'}).status_code, 400)
        self.member.refresh_from_db()
        self.assertFalse(self.member.profile_picture)

    def test_title_selection_reuses_grants_and_never_unlocks_new_titles(self):
        application = self.application()
        free = EditorTitle.objects.create(name='Free title')
        granted = EditorTitle.objects.create(name='Granted title', unlock_method='manual')
        locked = EditorTitle.objects.create(name='Locked title', unlock_method='manual')
        inactive = EditorTitle.objects.create(name='Inactive title', is_active=False)
        comment = EditorTitle.objects.create(name='Comment title', category='comment')
        UserTitleUnlock.objects.create(user=self.member, title=granted, unlock_method='manual')
        data = self.client.get(URL).json()
        self.assertEqual({item['id'] for item in data['titles']}, {free.pk, granted.pk})
        for title in (locked, inactive, comment):
            self.assertEqual(self.change(selected_title_id=title.pk).status_code, 403)
        response = self.change(selected_title_id=granted.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['member']['editor_title'], granted.name)
        application.refresh_from_db()
        self.assertEqual(application.selected_title_id, granted.pk)
        self.assertEqual(UserTitleUnlock.objects.count(), 1)
        self.assertEqual(self.change(selected_title_id='').json()['member']['editor_title'], 'Editor')

    def test_locked_or_inactive_existing_title_is_not_presented_as_available(self):
        self.application()
        title = EditorTitle.objects.create(name='Revoked title', unlock_method='manual')
        get_user_model().objects.filter(pk=self.member.pk).update(selected_title=title)
        data = self.client.get(URL).json()
        self.assertIsNone(data['profile']['selected_title_id'])
        self.assertEqual(data['member']['editor_title'], 'Editor')

    def test_forbidden_fields_and_malformed_inputs_do_not_change_identity(self):
        for data in ({'user': self.other.pk}, {'role': 'admin'}, {'username': 'Changed'}, {'email': 'changed@example.test'},
                     {'selected_title_id': True}, {'selected_title_id': '9' * 100}, {'profile_display_mode': ['channel']},
                     {'approved_channel_source': 'other'}, {'remove_picture': 'unexpected'}):
            self.assertEqual(self.change(**data).status_code, 400)
        self.assertEqual(self.client.post(URL, '[]', content_type='application/json').status_code, 400)
        self.member.refresh_from_db()
        self.assertEqual(self.member.username, 'ProfileMember')
        self.assertEqual(self.member.role, 'user')

    def test_delete_requires_confirmation_current_password_and_only_deletes_self(self):
        self.assertEqual(self.delete(password='Testing-123!').status_code, 400)
        self.assertEqual(self.delete(confirmation='DELETE', password='wrong').status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertEqual(self.delete(confirmation='DELETE', password='Testing-123!').status_code, 200)
        self.assertFalse(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_passwordless_delete_requires_recent_nonfuture_authentication(self):
        self.member.set_unusable_password()
        self.member.save(update_fields=['password'])
        self.client.force_login(self.member)
        self.assertEqual(self.delete(confirmation='DELETE').json()['code'], 'recent_login_required')
        for timestamp in (time.time() - 601, time.time() + 100, 'invalid'):
            session = self.client.session
            session['v2_authenticated_at'] = timestamp
            session.save()
            self.assertEqual(self.delete(confirmation='DELETE').status_code, 403)
        session = self.client.session
        session['v2_authenticated_at'] = time.time()
        session.save()
        self.assertEqual(self.delete(confirmation='DELETE').status_code, 200)

    def test_financial_history_blocks_deletion_without_partial_changes(self):
        product = Product(name='Protected order product', original_price='10.00', thumbnail='shop/example.png', main_image='shop/example.png')
        Product.objects.bulk_create([product])
        PaymentOrder.objects.create(user=self.member, product=product, idempotency_key=uuid4(), product_name=product.name,
            stripe_price_id='price_test', stripe_product_id='prod_test', currency='usd', amount_minor=1000,
            fulfillment_kind='digital_manual', fulfillment_note='Staff delivery')
        self.client.post(URL, {'profile_picture': self.image()})
        self.member.refresh_from_db()
        original = self.member.profile_picture.name
        response = self.delete(confirmation='DELETE', password='Testing-123!')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'protected_records')
        self.assertTrue(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertTrue(self.member.profile_picture.storage.exists(original))
        self.assertEqual(PaymentOrder.objects.count(), 1)
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_legacy_application_title_is_visible_and_can_be_cleared(self):
        title = EditorTitle.objects.create(name='Legacy Epic', rarity='epic')
        application = self.application()
        EditorApplication.objects.filter(pk=application.pk).update(selected_title=title)
        data = self.client.get(URL).json()
        self.assertEqual(data['profile']['selected_title_id'], title.pk)
        self.assertEqual(data['member']['editor_title_rarity'], 'epic')
        cleared = self.change(selected_title_id='').json()
        self.assertIsNone(cleared['member']['editor_title_rarity'])
        self.assertEqual(cleared['member']['editor_title'], 'Editor')
