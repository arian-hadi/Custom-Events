"""Standalone local V2 preview; never imports production settings or its .env.

Run: python manage.py runserver 127.0.0.1:8000 --settings=prime_project.settings_v2_local
The Next.js dev server proxies /api and uploads from localhost:5173.
"""
from pathlib import Path
import secrets

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_ROOT = BASE_DIR.parent / '.local-v2'
LOCAL_ROOT.mkdir(exist_ok=True)

# Only this optional, dedicated local file is ever read. DATABASE_URL and all
# production SMTP variables are ignored by this module.
env = environ.Env()
local_env = BASE_DIR.parent / '.env.v2.local'
if local_env.is_file():
    environ.Env.read_env(local_env)

secret_path = LOCAL_ROOT / 'django-secret.key'
try:
    with secret_path.open('x', encoding='utf-8') as secret_file:
        secret_file.write(secrets.token_hex(48))
except FileExistsError:
    pass
SECRET_KEY = env('V2_LOCAL_SECRET_KEY', default=secret_path.read_text(encoding='utf-8').strip())
DEBUG = True
V2_LOCAL_PREVIEW = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
ROOT_URLCONF = 'prime_project.urls'
WSGI_APPLICATION = 'prime_project.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'accounts', 'platform_api', 'django.contrib.admin', 'django.contrib.auth',
    'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages',
    'django.contrib.staticfiles', 'core.apps.CoreConfig', 'widget_tweaks',
    'django_ckeditor_5', 'contact', 'dashboard', 'events', 'announcements', 'shop',
    'edithub', 'notifications', 'tailwind', 'theme', 'ratelimit', 'django_summernote',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'accounts.middleware.V2EditorApplicationRedirectMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug', 'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
        'shop.context_processors.site_logo_context',
    ]},
}]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': LOCAL_ROOT / 'db.sqlite3'}}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'v2-local'}}
AUTH_USER_MODEL = 'accounts.CustomUser'
AUTHENTICATION_BACKENDS = ['accounts.authentication.EmailBackend', 'django.contrib.auth.backends.ModelBackend']
# Use the real Django hasher, never the fast MD5 test hasher in this preview.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher']
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = '/accounts/login/'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = LOCAL_ROOT / 'static'
STATICFILES_DIRS = [BASE_DIR / 'theme' / 'static_src']
MEDIA_URL = '/media/'
MEDIA_ROOT = LOCAL_ROOT / 'media'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']
CKEDITOR_5_CONFIGS = {'default': {'toolbar': ['heading', '|', 'bold', 'italic', 'link', 'bulletedList', 'numberedList', 'imageUpload']}}

# Files are a deliberate local outbox, not external email delivery.
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = LOCAL_ROOT / 'emails'
EMAIL_HOST_USER = 'website@platform-v2.test'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
SUPPORT_INBOX = 'support@platform-v2.test'
EMAIL_TIMEOUT = 10

V2_FRONTEND_URL = env('V2_LOCAL_FRONTEND_URL', default='http://localhost:5173').rstrip('/')
ADMIN_NOTIFICATION_RECIPIENTS = env('V2_LOCAL_ADMIN_NOTIFICATION_RECIPIENTS', default='')
ADMIN_NOTIFICATION_BASE_URL = V2_FRONTEND_URL
ADMIN_EMAIL_SEND_IMMEDIATELY = env.bool('V2_LOCAL_ADMIN_EMAIL_SEND_IMMEDIATELY', default=True)
CSRF_TRUSTED_ORIGINS = [V2_FRONTEND_URL, 'http://127.0.0.1:5173']
CSRF_FAILURE_VIEW = 'platform_api.views.csrf_failure'
SESSION_COOKIE_NAME = 'v2_local_sessionid'
CSRF_COOKIE_NAME = 'v2_local_csrftoken'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 900
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
ENABLE_EDITHUB_SCHEDULER = False
V2_TRUST_GATEWAY_ADDRESS = False
CORS_ALLOW_ALL_ORIGINS = False

GOOGLE_OAUTH_CLIENT_ID = env('V2_LOCAL_GOOGLE_OAUTH_CLIENT_ID', default='')
GOOGLE_OAUTH_CLIENT_SECRET = env('V2_LOCAL_GOOGLE_OAUTH_CLIENT_SECRET', default='')
GOOGLE_OAUTH_REDIRECT_URI = env('V2_LOCAL_GOOGLE_OAUTH_REDIRECT_URI', default='')
RECAPTCHA_SITE_KEY = env('V2_LOCAL_RECAPTCHA_SITE_KEY', default='')
RECAPTCHA_SECRET_KEY = env('V2_LOCAL_RECAPTCHA_SECRET_KEY', default='')
RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'
YOUTUBE_API_KEY = env('V2_LOCAL_YOUTUBE_API_KEY', default='')
YOUTUBE_BLOG_CREDENTIALS_FILE = env('V2_LOCAL_YOUTUBE_BLOG_CREDENTIALS_FILE', default='')
SUMMERNOTE_CONFIG = {"summernote": {"width": "100%"}}
LEAGUE_ENABLED = env.bool('V2_LOCAL_LEAGUE_ENABLED', default=False)
LEAGUE_PROVIDER_CREDENTIALS_FILE = env('V2_LOCAL_LEAGUE_PROVIDER_CREDENTIALS_FILE', default='')
LEAGUE_YOUTUBE_API_KEY = env('V2_LOCAL_LEAGUE_YOUTUBE_API_KEY', default='')

MEMBER_EMAIL_ENABLED = env.bool('V2_LOCAL_MEMBER_EMAIL_ENABLED', default=False)
MEMBER_ACTIVITY_EMAIL_ENABLED = env.bool('V2_LOCAL_MEMBER_ACTIVITY_EMAIL_ENABLED', default=False)
MEMBER_EMAIL_BASE_URL = V2_FRONTEND_URL
MEMBER_EMAIL_POSTAL_ADDRESS = env('V2_LOCAL_MEMBER_EMAIL_POSTAL_ADDRESS', default='Local preview — captured mail only')
STRIPE_CHECKOUT_ENABLED = env.bool('V2_LOCAL_STRIPE_CHECKOUT_ENABLED', default=False)
STRIPE_SECRET_KEY = env('V2_LOCAL_STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('V2_LOCAL_STRIPE_WEBHOOK_SECRET', default='')
# The isolated preview deliberately cannot enable real payments.
STRIPE_ALLOW_LIVE_PAYMENTS = False
STRIPE_CHECKOUT_BASE_URL = V2_FRONTEND_URL
AMAZON_AUTOMATION_ENABLED = env.bool('V2_LOCAL_AMAZON_AUTOMATION_ENABLED', default=False)
AMAZON_CREATORS_CLIENT_ID = env('V2_LOCAL_AMAZON_CREATORS_CLIENT_ID', default='')
AMAZON_CREATORS_CLIENT_SECRET = env('V2_LOCAL_AMAZON_CREATORS_CLIENT_SECRET', default='')
AMAZON_CREATORS_CREDENTIAL_VERSION = env('V2_LOCAL_AMAZON_CREATORS_CREDENTIAL_VERSION', default='3.1')
AMAZON_PARTNER_TAG = env('V2_LOCAL_AMAZON_PARTNER_TAG', default='')
AMAZON_MARKETPLACE = env('V2_LOCAL_AMAZON_MARKETPLACE', default='www.amazon.com')
AMAZON_REFRESH_MINUTES = env.int('V2_LOCAL_AMAZON_REFRESH_MINUTES', default=45)
AMAZON_HTTP_TIMEOUT = env.int('V2_LOCAL_AMAZON_HTTP_TIMEOUT', default=15)
