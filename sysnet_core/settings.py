"""
Django settings for the Sysnet Technologies platform.

Every deployment-specific value comes from environment variables with safe
development defaults, so the same settings file serves local dev, Docker
Compose, and production.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root if present (dev convenience; production
# should set real environment variables).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass


def env(key, default=''):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return os.environ.get(key, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_int(key, default):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key, default=''):
    return [h.strip() for h in os.environ.get(key, default).split(',') if h.strip()]


# ------------------------------------------------------------------ SECURITY
SECRET_KEY = env('SECRET_KEY', 'django-insecure-dev-only-key-change-me')
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'sysnet-ventures.onrender.com,localhost,127.0.0.1,0.0.0.0')
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:8000,http://127.0.0.1:8000,https://sysnet-ventures.onrender.com',
)

# HTTPS / proxy headers (set behind a reverse proxy that terminates TLS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', False)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Sessions: browser-lifetime sessions with server-side rotation on login.
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool('SESSION_EXPIRE_AT_BROWSER_CLOSE', False)
SESSION_COOKIE_AGE = env_int('SESSION_COOKIE_AGE', 60 * 60 * 12)  # 12 hours

# ------------------------------------------------------------------ APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sitemaps',
    'django.contrib.sites',
    'website',
    'accounts',
    'billing',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Simple in-DB rate limiting (see accounts/throttle.py) — works behind
# gunicorn without extra infrastructure. For heavy traffic put nginx limit_req
# zones in front.
THROTTLE_CONFIG = {
    'login': {'limit': int(env('THROTTLE_LOGIN_LIMIT', '10')), 'window_seconds': 300},
    'public_form': {'limit': int(env('THROTTLE_FORM_LIMIT', '10')), 'window_seconds': 3600},
}

ROOT_URLCONF = 'sysnet_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'billing.context_processors.company_info',
                'accounts.context_processors.portal_info',
            ],
        },
    },
]

WSGI_APPLICATION = 'sysnet_core.wsgi.application'

# ------------------------------------------------------------------ DATABASE
# PostgreSQL is the supported production database. Local bare-metal dev may
# fall back to SQLite when DATABASE_URL is unset.
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(
            os.environ['DATABASE_URL'],
            conn_max_age=env_int('CONN_MAX_AGE', 600),
            ssl_require=env_bool('PGSSLMODE_REQUIRE', False),
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'data' / 'db.sqlite3',
            'CONN_MAX_AGE': 60,
            'OPTIONS': {'timeout': 20},
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------------------------------ AUTH
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = [
    'accounts.backends.ThrottledModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/portal/login/'
LOGIN_REDIRECT_URL = '/portal/dashboard/'
LOGOUT_REDIRECT_URL = '/'
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # 24 hours

# ------------------------------------------------------------------ I18N
LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', 'Africa/Nairobi')
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------ STATIC & MEDIA
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', str(BASE_DIR / 'media'))

# WhiteNoise: disable manifest storage in DEBUG so dev iteration is instant
if DEBUG:
    STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}

# ------------------------------------------------------------------ FILE UPLOADS
# Client proof-of-payment uploads: allow common images + PDF, hard size cap.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_UPLOAD_SIZE_MB = env_int('MAX_UPLOAD_SIZE_MB', 5)
ALLOWED_UPLOAD_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}
ALLOWED_UPLOAD_CONTENT_TYPES = {
    'image/png', 'image/jpeg', 'image/webp', 'application/pdf',
}

# ------------------------------------------------------------------ EMAIL
# Console backend by default so local dev "just works" without credentials.
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = env('EMAIL_HOST', '')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'Sysnet Technologies <no-reply@localhost>')
STAFF_NOTIFY_EMAIL = env('STAFF_NOTIFY_EMAIL', '')
EMAIL_TIMEOUT = 15

# ------------------------------------------------------------------ LOGGING
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'billing.emails': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'accounts.throttle': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}


