"""Isolated V2 staging. A copied database must never activate live integrations."""
import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def _flag(name):
    return os.environ.get(name, '').lower() in {'true', '1', 'yes'}


_origin = os.environ.get('STAGING_PUBLIC_URL', '').rstrip('/')
_url = urlsplit(_origin)
if (_url.scheme not in {'http', 'https'} or not _url.hostname or _url.username or _url.password
        or _url.path or _url.query or _url.fragment):
    raise ImproperlyConfigured('STAGING_PUBLIC_URL must be one http(s) origin, including its public port if needed.')
if _url.scheme == 'http' and not _flag('STAGING_ALLOW_HTTP'):
    raise ImproperlyConfigured('HTTP staging requires explicit STAGING_ALLOW_HTTP=True. Prefer an SSH tunnel or HTTPS.')
_secret = os.environ.get('STAGING_SECRET_KEY', '')
if len(_secret) < 50 or _secret.lower().startswith(('replace', 'change', 'example')):
    raise ImproperlyConfigured('Set a fresh STAGING_SECRET_KEY of at least 50 characters; do not copy production credentials.')

# Import the shared application configuration without ever reading a legacy .env.
os.environ.update(DJANGO_READ_ENV_FILE='False', DEBUG='False', SECRET_KEY=_secret,
    ALLOWED_HOSTS=','.join(dict.fromkeys([_url.hostname, 'localhost', '127.0.0.1', 'backend'])),
    ENABLE_EDITHUB_SCHEDULER='False')
from .settings import *  # noqa: F403,E402

if DATABASES['default'].get('HOST') != 'db':  # noqa: F405
    raise ImproperlyConfigured('Staging must use its isolated Compose database service (host db).')
DEBUG = False
V2_FRONTEND_URL = _origin
CSRF_TRUSTED_ORIGINS = [_origin]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = []
SESSION_COOKIE_NAME = 'v2_staging_sessionid'
CSRF_COOKIE_NAME = 'v2_staging_csrftoken'
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = _url.scheme == 'https'
SECURE_SSL_REDIRECT = _url.scheme == 'https'
SECURE_HSTS_SECONDS = 0  # Do not apply a staging policy to other sites on the same IP.
ENABLE_EDITHUB_SCHEDULER = False
V2_TRUST_GATEWAY_ADDRESS = True

# Capture OTP, admin, campaign and transactional mail even if the restored DB
# includes real recipient addresses or an enabled campaign. No SMTP override.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST, EMAIL_PORT = 'mailpit', 1025
EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = 'staging@platform-v2.test'
ADMIN_NOTIFICATION_BASE_URL = MEMBER_EMAIL_BASE_URL = STRIPE_CHECKOUT_BASE_URL = _origin
STRIPE_ALLOW_LIVE_PAYMENTS = False
if STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith(('sk_test_', 'rk_test_')):  # noqa: F405
    raise ImproperlyConfigured('V2 staging accepts Stripe test keys only.')
