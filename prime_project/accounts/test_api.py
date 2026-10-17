import json
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from .api_views import verify_google_code
from .models import CustomUser, GoogleIdentity, OneTimePassword


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    V2_FRONTEND_URL='http://testserver',
    RECAPTCHA_SITE_KEY='', RECAPTCHA_SECRET_KEY='',
    GOOGLE_OAUTH_CLIENT_ID='', GOOGLE_OAUTH_CLIENT_SECRET='', GOOGLE_OAUTH_REDIRECT_URI='',
)
class AccountAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.password = 'A-complex-passphrase-4927'
        self.user = CustomUser.objects.create_user(
            email='member@example.com', username='existing_member', password=self.password,
            is_verified=True, is_active=True,
        )
        self.bootstrap()

    def bootstrap(self):
        response = self.client.get('/api/v2/auth/session/')
        self.csrf = response.json()['csrf_token']
        return response

    def post(self, path, data=None, **extra):
        return self.client.post(
            '/api/v2/auth/' + path + '/', json.dumps(data or {}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf, **extra,
        )

    def sign_in(self):
        response = self.post('login', {'email': self.user.email, 'password': self.password})
        self.csrf = response.json()['csrf_token']
        return response

    def test_session_is_uncached_and_does_not_expose_secrets(self):
        response = self.bootstrap()
        self.assertIsNone(response.json()['user'])
        self.assertFalse(response.json()['google_enabled'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn('GOOGLE_OAUTH_CLIENT_SECRET', response.content.decode())

    def test_login_requires_csrf_even_for_anonymous_requests(self):
        response = self.client.post('/api/v2/auth/login/', {
            'email': self.user.email, 'password': self.password,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verified_login_logout_and_token_rotation(self):
        old_token = self.csrf
        response = self.sign_in()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['id'], self.user.pk)
        self.assertNotEqual(old_token, self.csrf)
        self.assertEqual(self.post('logout').status_code, 200)
        self.assertIsNone(self.bootstrap().json()['user'])

    def test_inactive_verified_account_is_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.post('login', {'email': self.user.email, 'password': self.password})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verification_status_only_revealed_after_valid_password(self):
        self.user.is_verified = False
        self.user.save(update_fields=['is_verified'])
        wrong = self.post('login', {'email': self.user.email, 'password': 'wrong'})
        self.assertEqual(wrong.status_code, 401)
        self.assertNotIn('code', wrong.json())
        correct = self.post('login', {'email': self.user.email, 'password': self.password})
        self.assertEqual(correct.json()['code'], 'verification_required')

    @patch('accounts.forms.ENABLE_MX_CHECK', False)
    def test_registration_requires_email_verification_and_consumes_code(self):
        response = self.post('register', {
            'email': 'new.member@example.com', 'username': 'new_member',
            'password1': self.password, 'password2': self.password,
        })
        self.assertEqual(response.status_code, 201, response.content)
        user = CustomUser.objects.get(email='new.member@example.com')
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/verify-email?', mail.outbox[0].body)
        otp = OneTimePassword.objects.get(user=user)
        # Signup already sent exactly one code and retained the destination;
        # the verification screen need not ask the member for their email again.
        verified = self.post('verify-email', {'code': otp.code})
        self.assertEqual(verified.status_code, 200, verified.content)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_verified)
        self.assertFalse(OneTimePassword.objects.filter(user=user).exists())
        self.csrf = verified.json()['csrf_token']
        self.assertEqual(self.post('verify-email', {'code': otp.code, 'email': user.email}).status_code, 400)

    @patch('accounts.forms.ENABLE_MX_CHECK', False)
    @patch('accounts.api_views.send_mail', side_effect=OSError('SMTP unavailable'))
    def test_registration_mail_failure_does_not_claim_success(self, send):
        response = self.post('register', {
            'email': 'new.member@example.com', 'username': 'new_member',
            'password1': self.password, 'password2': self.password,
        })
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()['verification_required'])
        self.assertEqual(response.json()['code'], 'email_unavailable')
        self.assertTrue(CustomUser.objects.filter(email='new.member@example.com', is_active=False).exists())

    def test_verification_attempts_are_limited_by_account(self):
        self.user.is_verified = False
        self.user.save(update_fields=['is_verified'])
        for index in range(5):
            response = self.post('verify-email', {'email': self.user.email, 'code': '000000'}, REMOTE_ADDR=f'10.0.0.{index}')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post('verify-email', {'email': self.user.email, 'code': '000000'}, REMOTE_ADDR='10.0.0.8').status_code, 429)

    def test_profile_requires_authentication_and_cannot_escalate_permissions(self):
        self.assertEqual(self.client.get('/api/v2/auth/profile/').status_code, 401)
        self.sign_in()
        response = self.client.patch('/api/v2/auth/profile/', {
            'username': 'new_name', 'is_staff': True, 'role': 'admin',
        }, content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.role, 'user')
        response = self.client.patch('/api/v2/auth/profile/', {
            'username': 'new_name',
        }, content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['user']['username'], 'new_name')

    def test_password_reset_uses_single_use_token_and_keeps_response_generic(self):
        unknown = self.post('password-reset', {'email': 'unknown@example.com'})
        known = self.post('password-reset', {'email': self.user.email})
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith('http'))
        query = parse_qs(urlparse(link).query)
        data = {
            'uid': query['uid'][0], 'token': query['token'][0],
            'new_password1': 'Another-secure-passphrase-6927',
            'new_password2': 'Another-secure-passphrase-6927',
        }
        self.assertEqual(self.post('password-reset-confirm', data).status_code, 200)
        self.assertEqual(self.post('password-reset-confirm', data).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(data['new_password1']))

    def test_password_change_requires_existing_password(self):
        self.sign_in()
        response = self.post('password-change', {
            'old_password': 'wrong', 'new_password1': self.password, 'new_password2': self.password,
        })
        self.assertEqual(response.status_code, 400)

    def test_json_parser_rejects_nested_payloads(self):
        self.assertEqual(self.post('login', {'email': {'nested': 'bad'}}).status_code, 400)

    def test_google_is_unavailable_without_credentials(self):
        self.assertRedirects(self.client.get('/api/v2/auth/google/start/'),
                             'http://testserver/login?error=google_disabled', fetch_redirect_response=False)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID='test-client-id', GOOGLE_OAUTH_CLIENT_SECRET='test-secret',
    GOOGLE_OAUTH_REDIRECT_URI='http://testserver/api/v2/auth/google/callback/',
)
class GoogleAPITests(AccountAPITests):
    # Override the base-class settings context for this test class.
    def setUp(self):
        super().setUp()
        self.google_settings = override_settings(
            GOOGLE_OAUTH_CLIENT_ID='test-client-id', GOOGLE_OAUTH_CLIENT_SECRET='test-secret',
            GOOGLE_OAUTH_REDIRECT_URI='http://testserver/api/v2/auth/google/callback/',
        )
        self.google_settings.enable()
        self.addCleanup(self.google_settings.disable)

    def begin(self):
        response = self.client.get('/api/v2/auth/google/start/')
        query = parse_qs(urlparse(response['Location']).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertIn('nonce', query)
        return query['state'][0]

    def callback(self, state):
        return self.client.get('/api/v2/auth/google/callback/', {'state': state, 'code': 'opaque-code'})

    def test_session_is_uncached_and_does_not_expose_secrets(self):
        self.assertTrue(self.bootstrap().json()['google_enabled'])

    def test_google_is_unavailable_without_credentials(self):
        with override_settings(GOOGLE_OAUTH_CLIENT_SECRET=''):
            super().test_google_is_unavailable_without_credentials()

    @patch('accounts.api_views.verify_google_code')
    def test_invalid_state_rejected_without_token_exchange(self, verify):
        self.begin()
        response = self.callback('wrong-state')
        self.assertIn('error=google_failed', response['Location'])
        verify.assert_not_called()
        self.assertNotIn('v2_google_flow', self.client.session)

    @patch('accounts.api_views.verify_google_code')
    def test_expired_state_is_rejected(self, verify):
        state = self.begin()
        session = self.client.session
        session['v2_google_flow']['created_at'] = time.time() - 601
        session.save()
        self.assertIn('error=google_failed', self.callback(state)['Location'])
        verify.assert_not_called()

    @patch('accounts.api_views.verify_google_code')
    def test_existing_email_does_not_automatically_link(self, verify):
        verify.return_value = {'sub': 'unlinked-google-id', 'email': self.user.email, 'email_verified': True}
        response = self.callback(self.begin())
        self.assertIn('google_account_exists', response['Location'])
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    @patch('accounts.api_views.verify_google_code')
    def test_new_google_account_has_unusable_password(self, verify):
        verify.return_value = {'sub': 'new-google-id', 'email': 'new.google@gmail.com', 'email_verified': True}
        response = self.callback(self.begin())
        self.assertEqual(response['Location'], 'http://testserver/account')
        identity = GoogleIdentity.objects.get(subject='new-google-id')
        self.assertTrue(identity.user.is_verified)
        self.assertFalse(identity.user.has_usable_password())
        self.assertEqual(int(self.client.session['_auth_user_id']), identity.user_id)

    @patch('accounts.api_views.verify_google_code')
    def test_third_party_google_email_requires_site_verification(self, verify):
        verify.return_value = {'sub': 'third-party-id', 'email': 'third.party@example.com', 'email_verified': True}
        response = self.callback(self.begin())
        self.assertIn('/verify-email?', response['Location'])
        user = GoogleIdentity.objects.get(subject='third-party-id').user
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_active)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(len(mail.outbox), 1)

    @patch('accounts.api_views.verify_google_code')
    def test_authenticated_explicit_link_then_login_by_subject(self, verify):
        self.sign_in()
        response = self.post('google/link')
        state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
        verify.return_value = {'sub': 'linked-google-id', 'email': 'different@gmail.com', 'email_verified': True}
        self.assertEqual(self.callback(state)['Location'], 'http://testserver/account/settings')
        self.assertEqual(GoogleIdentity.objects.get(subject='linked-google-id').user_id, self.user.pk)
        self.post('logout')
        self.bootstrap()
        self.assertEqual(self.callback(self.begin())['Location'], 'http://testserver/account')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    @patch('accounts.api_views.verify_google_code')
    def test_link_cannot_complete_after_user_logs_out(self, verify):
        self.sign_in()
        response = self.post('google/link')
        state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
        self.post('logout')
        response = self.callback(state)
        self.assertIn('google_failed', response['Location'])
        verify.assert_not_called()

    @patch('google.oauth2.id_token.verify_oauth2_token')
    @patch('accounts.api_views.requests.post')
    def test_google_nonce_and_verified_email_are_checked(self, post, verify):
        post.return_value.json.return_value = {'id_token': 'opaque-id-token'}
        verify.return_value = {'nonce': 'wrong', 'sub': 'subject', 'email': 'someone@gmail.com', 'email_verified': True}
        with self.assertRaises(ValueError):
            verify_google_code('code', {'verifier': 'pkce', 'nonce': 'expected'})
        verify.return_value['nonce'] = 'expected'
        verify.return_value['email_verified'] = False
        with self.assertRaises(ValueError):
            verify_google_code('code', {'verifier': 'pkce', 'nonce': 'expected'})
        verify.return_value['email_verified'] = True
        claims = verify_google_code('code', {'verifier': 'pkce', 'nonce': 'expected'})
        self.assertEqual(claims['sub'], 'subject')
        self.assertEqual(verify.call_args.args[2], settings.GOOGLE_OAUTH_CLIENT_ID)
