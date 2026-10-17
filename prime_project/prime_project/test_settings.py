"""Isolated test configuration: never reads .env or connects to production services."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "only-for-isolated-tests-not-for-deployment"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
ROOT_URLCONF = "prime_project.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.CustomUser"
AUTHENTICATION_BACKENDS = ["accounts.authentication.EmailBackend", "django.contrib.auth.backends.ModelBackend"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "accounts", "core", "contact", "dashboard",
    "events", "announcements", "shop", "edithub", "notifications", "platform_api",
    "prime_project.summernote_app.SummernoteConfig",
    "django_ckeditor_5", "widget_tweaks",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]},
}]
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
SUMMERNOTE_CONFIG = {"summernote": {"width": "100%"}}
MEDIA_ROOT = BASE_DIR / ".test-media"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST_USER = "website@example.test"
DEFAULT_FROM_EMAIL = "website@example.test"
SUPPORT_INBOX = "support@example.test"
ENABLE_EDITHUB_SCHEDULER = False
CSRF_FAILURE_VIEW = "platform_api.views.csrf_failure"
RECAPTCHA_SITE_KEY = ""
RECAPTCHA_SECRET_KEY = ""
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
GOOGLE_OAUTH_CLIENT_ID = ""
GOOGLE_OAUTH_CLIENT_SECRET = ""
GOOGLE_OAUTH_REDIRECT_URI = ""
V2_GOOGLE_LOGIN_ENABLED = False
V2_FRONTEND_URL = "http://testserver"
V2_AUTH_RATE_LIMIT = 20
LOGIN_URL = "/accounts/login/"
