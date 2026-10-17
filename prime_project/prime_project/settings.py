from pathlib import Path
from datetime import timedelta
import environ

import os
BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
# Compose supplies its own isolated environment. A development source mount may
# contain the legacy .env, which must never configure the V2 containers.
if env.bool('DJANGO_READ_ENV_FILE', default=True):
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG")  # Reads from .env, defaults to True if missing


# ALLOWED_HOSTS = [
#     'localhost',
#     '127.0.0.1',
#     '20transformers.com',
#     'www.20transformers.com'
# ]

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
)
 
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Application definition

INSTALLED_APPS = [
    'accounts',
    'platform_api',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'core.apps.CoreConfig',
    'widget_tweaks',
    'django_ckeditor_5',
    'contact',
    'dashboard',
    'events',
    'announcements',
    'shop',
    'edithub',
    'notifications',
    'tailwind',
    'theme',
    'ratelimit',
    'prime_project.summernote_app.SummernoteConfig',
]


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15), 
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1), 
    'AUTH_HEADER_TYPES': ('Bearer',),
}


INTERNAL_IPS = [
    "127.0.0.1",
]

NPM_BIN_PATH = "C:/Program Files/nodejs/npm.cmd"

TAILWIND_APP_NAME = 'theme'

# #mailjet system
# #EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_MAILJET_HOST = 'in-v3.mailjet.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_API = env('apo')
# EMAIL_HOST_SECRET_KEY = env(secret_key)
# DEFAULT_FROM_EMAIL = email_address


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'accounts.middleware.TrustedGatewayAddressMiddleware',
    'accounts.middleware.V2EditorApplicationRedirectMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
]

CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=True)
CSRF_FAILURE_VIEW = 'platform_api.views.csrf_failure'
ROOT_URLCONF = 'prime_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'shop.context_processors.site_logo_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'prime_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': env("DB_NAME"),
#         'USER': env("DB_USER"),
#         'PASSWORD': env("DB_PASSWORD"),
#         'HOST': env("DB_HOST"),
#         'PORT': env.int("DB_PORT"),
#     }
# }

import dj_database_url
# Default database setup
DATABASES = {
    'default': dj_database_url.config(default=os.getenv("DATABASE_URL"))
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "theme", "static_src"),  # Your Tailwind output
]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")  # collectstatic destination

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'mediafiles')

# File upload settings - allow up to 10MB to match nginx configuration
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Django CKEditor 5 Settings
customColorPalette = [
    {
        'color': 'hsl(4, 90%, 58%)',
        'label': 'Red'
    },
    {
        'color': 'hsl(340, 82%, 52%)',
        'label': 'Pink'
    },
    {
        'color': 'hsl(291, 64%, 42%)',
        'label': 'Purple'
    },
    {
        'color': 'hsl(262, 52%, 47%)',
        'label': 'Deep Purple'
    },
    {
        'color': 'hsl(231, 48%, 48%)',
        'label': 'Indigo'
    },
    {
        'color': 'hsl(207, 90%, 54%)',
        'label': 'Blue'
    },
]

CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': ['heading', '|', 'bold', 'italic', 'link',
                    'bulletedList', 'numberedList', 'blockQuote', 'imageUpload', ],

    },
    'extends': {
        'blockToolbar': [
            'paragraph', 'heading1', 'heading2', 'heading3',
            '|',
            'bulletedList', 'numberedList',
            '|',
            'blockQuote',
        ],
        'toolbar': ['heading', '|', 'outdent', 'indent', '|', 'bold', 'italic', 'link', 'underline', 'strikethrough',
        'code','subscript', 'superscript', 'highlight', '|', 'codeBlock', 'sourceEditing', 'insertImage',
                    'bulletedList', 'numberedList', 'todoList', '|',  'blockQuote', 'imageUpload', '|',
                    'fontSize', 'fontFamily', 'fontColor', 'fontBackgroundColor', 'mediaEmbed', 'removeFormat',
                    'insertTable',],
        'image': {
            'toolbar': ['imageTextAlternative', '|', 'imageStyle:alignLeft',
                        'imageStyle:alignRight', 'imageStyle:alignCenter', 'imageStyle:side',  '|'],
            'styles': [
                'full',
                'side',
                'alignLeft',
                'alignRight',
                'alignCenter',
            ]

        },
        'table': {
            'contentToolbar': [ 'tableColumn', 'tableRow', 'mergeTableCells',
            'tableProperties', 'tableCellProperties' ],
            'tableProperties': {
                'borderColors': customColorPalette,
                'backgroundColors': customColorPalette
            },
            'tableCellProperties': {
                'borderColors': customColorPalette,
                'backgroundColors': customColorPalette
            }
        },
        'heading' : {
            'options': [
                { 'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph' },
                { 'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1' },
                { 'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2' },
                { 'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3' }
            ]
        }
    },
    'list': {
        'properties': {
            'styles': 'true',
            'startIndex': 'true',
            'reversed': 'true',
        }
    }
}




import sys

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
        },
    },
    # Send everything to console at INFO+ by default
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        # Django framework logs at INFO+ and do NOT propagate to root (avoids duplicates)
        "django": {
            "handlers": ["console"],
            "level": "INFO",      # use "WARNING" for even less noise
            "propagate": False,
        },
        # Silence the autoreloader’s DEBUG spam specifically
        "django.utils.autoreload": {
            "handlers": ["console"],
            "level": "WARNING",   # or "ERROR" to hide almost all of it
            "propagate": False,
        },
    },
}

# Default primary key field type

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.CustomUser'


AUTHENTICATION_BACKENDS = [
    'accounts.authentication.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# CSRF_TRUSTED_ORIGINS = [
#     "https://personal-website-production-fc26.up.railway.app",
#     "https://20transformers.com",
# ]

# Parse CSRF_TRUSTED_ORIGINS manually to preserve ports in URLs
# django-environ's env.list() strips ports from URLs, so we parse the raw string
csrf_origins_str = os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost")
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins_str.split(",") if origin.strip()]

#Email verification
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER or 'noreply@localhost')
SUPPORT_INBOX = env('SUPPORT_EMAIL', default='support@localhost')
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



SESSION_COOKIE_AGE = 900  # 900 seconds = 15 minutes
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = env('SESSION_COOKIE_NAME', default='sessionid')
CSRF_COOKIE_NAME = env('CSRF_COOKIE_NAME', default='csrftoken')
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=not DEBUG)

# V2 uses one public origin (Next.js + Django behind the gateway). Google
# credentials stay server-side; supplying all three values enables sign-in.
V2_FRONTEND_URL = env('V2_FRONTEND_URL', default='http://localhost:8082').rstrip('/')
ADMIN_NOTIFICATION_RECIPIENTS = env('ADMIN_NOTIFICATION_RECIPIENTS', default='')
ADMIN_NOTIFICATION_BASE_URL = env('ADMIN_NOTIFICATION_BASE_URL', default=V2_FRONTEND_URL)
ADMIN_EMAIL_SEND_IMMEDIATELY = env.bool('ADMIN_EMAIL_SEND_IMMEDIATELY', default=True)
GOOGLE_OAUTH_CLIENT_ID = env('GOOGLE_OAUTH_CLIENT_ID', default='')
GOOGLE_OAUTH_CLIENT_SECRET = env('GOOGLE_OAUTH_CLIENT_SECRET', default='')
GOOGLE_OAUTH_REDIRECT_URI = env('GOOGLE_OAUTH_REDIRECT_URI', default='')
ENABLE_EDITHUB_SCHEDULER = env.bool('ENABLE_EDITHUB_SCHEDULER', default=True)
LEAGUE_ENABLED = env.bool('LEAGUE_ENABLED', default=False)
LEAGUE_PROVIDER_CREDENTIALS_FILE = env('LEAGUE_PROVIDER_CREDENTIALS_FILE', default='')
LEAGUE_YOUTUBE_API_KEY = env('LEAGUE_YOUTUBE_API_KEY', default='')

# Optional V2 integrations. Keys are server-side and activation is explicit.
MEMBER_EMAIL_ENABLED = env.bool('MEMBER_EMAIL_ENABLED', default=False)
MEMBER_ACTIVITY_EMAIL_ENABLED = env.bool('MEMBER_ACTIVITY_EMAIL_ENABLED', default=False)
MEMBER_EMAIL_BASE_URL = env('MEMBER_EMAIL_BASE_URL', default='')
MEMBER_EMAIL_POSTAL_ADDRESS = env('MEMBER_EMAIL_POSTAL_ADDRESS', default='')
STRIPE_CHECKOUT_ENABLED = env.bool('STRIPE_CHECKOUT_ENABLED', default=False)
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')
STRIPE_ALLOW_LIVE_PAYMENTS = env.bool('STRIPE_ALLOW_LIVE_PAYMENTS', default=False)
STRIPE_CHECKOUT_BASE_URL = env('STRIPE_CHECKOUT_BASE_URL', default='')
AMAZON_AUTOMATION_ENABLED = env.bool('AMAZON_AUTOMATION_ENABLED', default=False)
AMAZON_CREATORS_CLIENT_ID = env('AMAZON_CREATORS_CLIENT_ID', default='')
AMAZON_CREATORS_CLIENT_SECRET = env('AMAZON_CREATORS_CLIENT_SECRET', default='')
AMAZON_CREATORS_CREDENTIAL_VERSION = env('AMAZON_CREATORS_CREDENTIAL_VERSION', default='3.1')
AMAZON_PARTNER_TAG = env('AMAZON_PARTNER_TAG', default='')
AMAZON_MARKETPLACE = env('AMAZON_MARKETPLACE', default='www.amazon.com')
AMAZON_REFRESH_MINUTES = env.int('AMAZON_REFRESH_MINUTES', default=45)
AMAZON_HTTP_TIMEOUT = env.int('AMAZON_HTTP_TIMEOUT', default=15)
V2_TRUST_GATEWAY_ADDRESS = env.bool('V2_TRUST_GATEWAY_ADDRESS', default=False)

# Google reCAPTCHA Settings
# Get your keys from: https://www.google.com/recaptcha/admin
RECAPTCHA_SITE_KEY = env("RECAPTCHA_SITE_KEY", default="")
RECAPTCHA_SECRET_KEY = env("RECAPTCHA_SECRET_KEY", default="")
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

# YouTube Data API v3 Settings (for EditingHub channel data fetching)
# Get your API key from: https://console.cloud.google.com/apis/credentials
# Note: TikTok channel data is fetched via web scraping (no API key required)
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY", default="")
YOUTUBE_BLOG_CREDENTIALS_FILE = env("YOUTUBE_BLOG_CREDENTIALS_FILE", default="")
SUMMERNOTE_CONFIG = {"summernote": {"width": "100%"}}
