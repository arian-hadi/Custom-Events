"""Session-based V2 account API. All browser mutations require Django CSRF."""

import base64
import hashlib
import json
import logging
import secrets
import time
from functools import wraps
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from notifications.email_design import email_html, text_content
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .forms import CustomUserCreationForm, ProfileUpdateForm
from .models import CustomUser, GoogleIdentity, OneTimePassword

logger = logging.getLogger(__name__)
AUTH_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def error(detail, status=400, **extra):
    return JsonResponse({'detail': detail, **extra}, status=status)


def limited(request, scope, limit=10, period=600, identity=''):
    # REMOTE_ADDR is trusted only when the gateway overwrites it. Never consume
    # user-controlled X-Forwarded-For directly. An identity limit supplements IP.
    identities = [request.META.get('REMOTE_ADDR', '')]
    if identity:
        identities.append('account:' + identity.lower())
    for value in identities:
        digest = hashlib.sha256(value.encode()).hexdigest()
        key = f'v2:auth:{scope}:{digest}'
        if cache.add(key, 1, timeout=period):
            continue
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=period)
            attempts = 1
        if attempts > limit:
            return True
    return False


def api(methods=('POST',), authenticated=False):
    def decorator(view):
        @wraps(view)
        @never_cache
        @csrf_protect
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = error('Method not allowed.', 405)
                response['Allow'] = ', '.join(methods)
                return response
            if authenticated and (
                not request.user.is_authenticated or not request.user.is_active
            ):
                return error('Please sign in to continue.', 401)
            data = {}
            if request.method != 'GET':
                if request.content_type != 'application/json':
                    return error('Send a JSON request body.', 415)
                try:
                    data = json.loads(request.body or b'{}')
                except (ValueError, UnicodeDecodeError):
                    return error('Invalid JSON request body.')
                if not isinstance(data, dict) or any(
                    not isinstance(value, (str, bool, int, float, type(None)))
                    for value in data.values()
                ):
                    return error('Expected a JSON object containing simple fields.')
            return view(request, data, *args, **kwargs)
        return wrapped
    return decorator


def text_field(data, name):
    value = data.get(name, '')
    return value if isinstance(value, str) else ''


def user_data(user):
    if not user.is_authenticated or not user.is_active:
        return None
    return {
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'is_verified': user.is_verified,
        'is_staff': user.is_staff,
        'role': user.role,
        'profile_picture': user.get_display_picture(),
        'google_linked': GoogleIdentity.objects.filter(user=user).exists(),
        'has_password': user.has_usable_password(),
    }


def google_enabled():
    return all(getattr(settings, key, '') for key in (
        'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET', 'GOOGLE_OAUTH_REDIRECT_URI'
    ))


def session_payload(request):
    return {
        'user': user_data(request.user),
        'csrf_token': get_token(request),
        'google_enabled': google_enabled(),
        'recaptcha_site_key': getattr(settings, 'RECAPTCHA_SITE_KEY', '')
        if getattr(settings, 'RECAPTCHA_SECRET_KEY', '') else '',
    }


@never_cache
@ensure_csrf_cookie
@require_GET
def session_view(request):
    return JsonResponse(session_payload(request))


def recaptcha_valid(data):
    site_key = getattr(settings, 'RECAPTCHA_SITE_KEY', '')
    secret = getattr(settings, 'RECAPTCHA_SECRET_KEY', '')
    if not site_key and not secret:
        return True
    token = text_field(data, 'recaptcha_token')
    if not token or not site_key or not secret:
        return False
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': secret, 'response': token}, timeout=10,
        )
        response.raise_for_status()
        return response.json().get('success') is True
    except (requests.RequestException, ValueError):
        return False


def frontend_url(path, params=None):
    url = getattr(settings, 'V2_FRONTEND_URL', 'http://localhost:8082').rstrip('/') + path
    return url + ('?' + urlencode(params) if params else '')


def send_verification(user):
    # Reuse the existing OTP records/expiry while generating codes securely.
    code = f'{secrets.randbelow(1000000):06d}'
    with transaction.atomic():
        CustomUser.objects.select_for_update().get(pk=user.pk)
        OneTimePassword.objects.filter(user=user).delete()
        OneTimePassword.objects.create(user=user, code=code)
    url = frontend_url('/verify-email', {'email': user.email})
    sent = send_mail(
        'Verify your 20Transformers account',
        f'Hi {user.username},\n\nYour verification code is {code}. It expires in 10 minutes.\n\n'
        f'Enter it here: {url}\n\nIf you did not request this, ignore this message.',
        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
        html_message=email_html('Verify your account', text_content(
            f'Hi {user.username},\n\nEnter this code to verify your email. It expires in 10 minutes.\n\n'
            'If you did not request this, ignore this message.'),
            action_url=url, action_label='Verify email', code=code),
    )
    if not sent:
        raise RuntimeError('Email backend did not accept verification message')


@api()
def register_view(request, data):
    if limited(request, 'register', limit=10, period=3600):
        return error('Too many registration attempts. Please try again later.', 429)
    if not recaptcha_valid(data):
        return error('Please complete the security check.', code='recaptcha_required')
    form = CustomUserCreationForm(data)
    if not form.is_valid():
        return error('Please check the registration fields.', errors=dict(form.errors))
    email = form.cleaned_data['email']
    if CustomUser.objects.filter(email__iexact=email).exists():
        return error('An account already uses this email.', errors={'email': ['Already registered.']})
    try:
        with transaction.atomic():
            user = form.save(commit=False)
            user.is_active = False
            user.is_verified = False
            user.save()
    except IntegrityError:
        return error('This email or username is already registered.', 409)
    request.session['user_email'] = user.email
    request.session['registration_time'] = int(time.time())
    try:
        send_verification(user)
    except Exception:
        logger.warning('V2 verification email delivery failed for account %s', user.pk)
        return error(
            'Account created, but verification email could not be delivered. Please request a new code.',
            503, verification_required=True, email=user.email, code='email_unavailable',
        )
    return JsonResponse({
        'verification_required': True, 'email': user.email,
        'detail': 'Account created. Check your email for a verification code.',
    }, status=201)


@api()
def login_view(request, data):
    email = text_field(data, 'email').strip().lower()
    password = text_field(data, 'password')
    if limited(request, 'login', limit=15, identity=email):
        return error('Too many sign-in attempts. Please try again later.', 429)
    user = CustomUser.objects.filter(email__iexact=email).first()
    if not user:
        make_password(password)  # Keep the password hashing cost for unknown users.
        return error('Invalid email or password.', 401)
    if not password or not user.check_password(password):
        return error('Invalid email or password.', 401)
    if not user.is_verified:
        request.session['user_email'] = user.email
        return error('Verify your email before signing in.', 403, code='verification_required')
    if not user.is_active:
        return error('This account is unavailable.', 403)
    login(request, user, backend=AUTH_BACKEND)
    request.session['v2_authenticated_at'] = time.time()
    return JsonResponse(session_payload(request))


@api()
def logout_view(request, data):
    logout(request)
    return JsonResponse(session_payload(request))


@api()
def verify_email(request, data):
    email = text_field(data, 'email').strip().lower() or request.session.get('user_email', '')
    code = text_field(data, 'code').strip()
    if limited(request, 'verify', limit=5, period=600, identity=email):
        return error('Too many verification attempts. Please wait before trying again.', 429)
    with transaction.atomic():
        user = CustomUser.objects.select_for_update().filter(email__iexact=email, is_verified=False).first()
        otp = OneTimePassword.objects.filter(user=user, code=code).first() if user else None
        if not otp or otp.is_expired():
            return error('Invalid or expired verification code.')
        user.is_verified = True
        user.is_active = True
        user.save(update_fields=['is_verified', 'is_active'])
        OneTimePassword.objects.filter(user=user).delete()
    request.session.pop('user_email', None)
    request.session.pop('registration_time', None)
    login(request, user, backend=AUTH_BACKEND)
    request.session['v2_authenticated_at'] = time.time()
    return JsonResponse(session_payload(request))


@api()
def resend_verification(request, data):
    email = text_field(data, 'email').strip().lower()
    if limited(request, 'resend', limit=3, period=600, identity=email):
        return error('Too many requests. Please wait before requesting another code.', 429)
    if not recaptcha_valid(data):
        return error('Please complete the security check.', code='recaptcha_required')
    user = CustomUser.objects.filter(email__iexact=email, is_verified=False).first()
    if user:
        request.session['user_email'] = user.email
        try:
            send_verification(user)
        except Exception:
            logger.warning('V2 verification email delivery failed for account %s', user.pk)
            return error('Email is temporarily unavailable. Please try again later.', 503)
    return JsonResponse({'detail': 'If this account needs verification, a new code has been sent.'})


@api()
def password_reset(request, data):
    email = text_field(data, 'email').strip().lower()
    if limited(request, 'reset', limit=5, period=3600, identity=email):
        return error('Too many reset requests. Please try again later.', 429)
    if not recaptcha_valid(data):
        return error('Please complete the security check.', code='recaptcha_required')
    try:
        validate_email(email)
    except ValidationError:
        return error('Enter a valid email address.', errors={'email': ['Enter a valid email address.']})
    user = CustomUser.objects.filter(email__iexact=email, is_active=True, is_verified=True).first()
    # A verified Google account can set its first password by proving control
    # of the website email, using the same single-use Django reset token.
    if user:
        url = frontend_url('/reset-password', {
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': default_token_generator.make_token(user),
        })
        try:
            sent = send_mail(
                'Reset your 20Transformers password',
                f'Use this link to set a new password:\n\n{url}\n\n'
                'If you did not request this, ignore this message.',
                settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
                html_message=email_html('Reset your password', text_content(
                    'Use the button below to set a new password.\n\nIf you did not request this, ignore this message.'),
                    action_url=url, action_label='Reset password'),
            )
            if not sent:
                raise RuntimeError('Email backend did not accept reset message')
        except Exception:
            logger.warning('V2 reset email delivery failed for account %s', user.pk)
            return error('Email is temporarily unavailable. Please try again later.', 503)
    return JsonResponse({'detail': 'If an eligible account exists, password reset instructions have been sent.'})


@api()
def password_reset_confirm(request, data):
    if limited(request, 'reset-confirm', limit=15):
        return error('Too many attempts. Please try again later.', 429)
    try:
        uid = force_str(urlsafe_base64_decode(text_field(data, 'uid')))
        user = CustomUser.objects.get(pk=uid, is_active=True, is_verified=True)
    except (ValueError, TypeError, OverflowError, UnicodeDecodeError, CustomUser.DoesNotExist):
        user = None
    if not user or not default_token_generator.check_token(user, text_field(data, 'token')):
        return error('This reset link is invalid or expired.')
    form = SetPasswordForm(user, data)
    if not form.is_valid():
        return error('Please check your new password.', errors=dict(form.errors))
    form.save()
    return JsonResponse({'detail': 'Password updated. You can now sign in.'})


@api(authenticated=True)
def password_change(request, data):
    if limited(request, 'password-change', limit=10, identity=str(request.user.pk)):
        return error('Too many attempts. Please try again later.', 429)
    form = PasswordChangeForm(request.user, data)
    if not form.is_valid():
        return error('Please check your password fields.', errors=dict(form.errors))
    user = form.save()
    update_session_auth_hash(request, user)
    return JsonResponse(session_payload(request))


@api(methods=('GET', 'PATCH'), authenticated=True)
def profile(request, data):
    if request.method == 'PATCH':
        if set(data) - {'username'}:
            return error('Only the username can be changed here. Email changes require a separate verification flow.')
        # Reuse the established username policy without rewriting verified email.
        form = ProfileUpdateForm({'username': text_field(data, 'username'), 'email': request.user.email}, user=request.user)
        try:
            form.cleaned_data = {'username': text_field(data, 'username')}
            username = form.clean_username()
        except ValidationError as exc:
            return error('Please check your username.', errors={'username': exc.messages})
        request.user.username = username
        try:
            with transaction.atomic():
                request.user.save(update_fields=['username'])
        except IntegrityError:
            return error('This username is already in use.', 409)
    return JsonResponse(session_payload(request))


def google_authorization_url(request, link_user_id=None):
    flow = {
        'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
        'verifier': secrets.token_urlsafe(64), 'created_at': time.time(),
        'link_user_id': link_user_id,
    }
    request.session['v2_google_flow'] = flow
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow['verifier'].encode()).digest()).rstrip(b'=').decode()
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code', 'scope': 'openid email profile',
        'state': flow['state'], 'nonce': flow['nonce'], 'prompt': 'select_account',
        'code_challenge': challenge, 'code_challenge_method': 'S256',
    })


@never_cache
@require_GET
def google_start(request):
    if not google_enabled():
        return HttpResponseRedirect(frontend_url('/login', {'error': 'google_disabled'}))
    return HttpResponseRedirect(google_authorization_url(request))


@api(authenticated=True)
def google_link(request, data):
    if not google_enabled():
        return error('Google sign-in is not configured.', 503)
    if not request.user.is_verified:
        return error('Verify your website email first.', 403)
    if limited(request, 'google-link', limit=10, identity=str(request.user.pk)):
        return error('Too many attempts. Please try again later.', 429)
    return JsonResponse({'authorization_url': google_authorization_url(request, request.user.pk)})


def verify_google_code(code, flow):
    """Google's maintained verifier checks JWT signature, issuer, expiry and audience."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    response = requests.post('https://oauth2.googleapis.com/token', data={
        'code': code, 'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type': 'authorization_code', 'code_verifier': flow['verifier'],
    }, timeout=10)
    response.raise_for_status()
    transport = Request()

    def bounded_request(*args, **kwargs):
        kwargs['timeout'] = 10
        return transport(*args, **kwargs)

    claims = id_token.verify_oauth2_token(
        response.json()['id_token'], bounded_request, settings.GOOGLE_OAUTH_CLIENT_ID,
    )
    if not constant_time_compare(str(claims.get('nonce', '')), flow['nonce']):
        raise ValueError('Invalid nonce')
    if claims.get('email_verified') is not True or not claims.get('sub'):
        raise ValueError('Unverified identity')
    if claims.get('azp', settings.GOOGLE_OAUTH_CLIENT_ID) != settings.GOOGLE_OAUTH_CLIENT_ID:
        raise ValueError('Invalid authorized party')
    validate_email(claims.get('email', ''))
    return claims


@never_cache
@require_GET
def google_callback(request):
    failure = lambda code='google_failed': HttpResponseRedirect(frontend_url('/login', {'error': code}))
    # Consume state before any work so callbacks cannot be replayed.
    flow = request.session.pop('v2_google_flow', None)
    if not google_enabled():
        return failure('google_disabled')
    if (
        not flow or time.time() - flow.get('created_at', 0) > 600
        or not constant_time_compare(request.GET.get('state', ''), flow.get('state', ''))
        or not request.GET.get('code') or request.GET.get('error')
    ):
        return failure()
    try:
        claims = verify_google_code(request.GET['code'], flow)
    except Exception:
        logger.warning('Google sign-in token verification failed')
        return failure()
    email = claims['email'].strip().lower()
    subject = claims['sub']
    linking = flow.get('link_user_id')
    try:
        with transaction.atomic():
            identity = GoogleIdentity.objects.select_related('user').filter(subject=subject).first()
            if linking:
                if (
                    not request.user.is_authenticated or request.user.pk != linking
                    or not request.user.is_active or not request.user.is_verified
                    or (identity and identity.user_id != linking)
                ):
                    return failure('google_link_failed')
                current = GoogleIdentity.objects.filter(user=request.user).first()
                if current and current.subject != subject:
                    return failure('google_link_failed')
                GoogleIdentity.objects.get_or_create(subject=subject, defaults={'user': request.user})
                return HttpResponseRedirect(frontend_url('/account/settings'))
            if identity:
                user = identity.user
            elif CustomUser.objects.filter(email__iexact=email).exists():
                # Email coincidence is not proof of control of a website account.
                return failure('google_account_exists')
            else:
                # Google is authoritative for Gmail/Workspace, but not arbitrary
                # third-party addresses. Those still complete our OTP challenge.
                authoritative = email.endswith('@gmail.com') or bool(claims.get('hd'))
                user = CustomUser.objects.create_user(
                    email=email, username='member_' + secrets.token_hex(8),
                    is_active=authoritative, is_verified=authoritative,
                )
                GoogleIdentity.objects.create(user=user, subject=subject)
    except IntegrityError:
        return failure('google_account_exists')
    if not user.is_verified:
        request.session['user_email'] = user.email
        try:
            send_verification(user)
        except Exception:
            logger.warning('Google account verification email delivery failed for account %s', user.pk)
            return failure('google_email_unavailable')
        return HttpResponseRedirect(frontend_url('/verify-email', {'email': user.email}))
    if not user.is_active:
        return failure()
    login(request, user, backend=AUTH_BACKEND)
    request.session['v2_authenticated_at'] = time.time()
    return HttpResponseRedirect(frontend_url('/account'))


