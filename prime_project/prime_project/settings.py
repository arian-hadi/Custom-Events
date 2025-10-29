from pathlib import Path
from datetime import timedelta
import environ

import os
BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
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
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'core.apps.CoreConfig',
    'widget_tweaks',
    'contact',
    'dashboard',
    'events',
    'announcements',
    'tailwind',
    'theme',
    'ratelimit'
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
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
]

CORS_ALLOW_ALL_ORIGINS = True
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

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost"]
)

#Email verification
EMAIL_BACKEND = env("EMAIL_BACKEND") 
EMAIL_HOST = env("EMAIL_HOST") 
EMAIL_HOST_USER = env("EMAIL_HOST_USER")  # Your Gmail address
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD") # Your Gmail app password
DEFAULT_FROM_EMAIL = env("EMAIL_HOST_USER") 
SUPPORT_INBOX = env("SUPPORT_EMAIL") # Support email address
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_PORT = env.int("EMAIL_PORT", default=587)


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



SESSION_COOKIE_AGE = 900  # 900 seconds = 15 minutes
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
