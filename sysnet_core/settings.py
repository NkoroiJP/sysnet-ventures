"""
Django settings for sysnet_core project.

All deployment-specific values come from environment variables with safe
development defaults so the same settings file works in dev and production.
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


def env(key, default):
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


# SECURITY
SECRET_KEY = env('SECRET_KEY', 'django-insecure-dev-only-key-change-me')
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0')
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:8000,http://127.0.0.1:8000',
)

# HTTPS / proxy headers (set behind a reverse proxy that terminates TLS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', False)
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# APPLICATION DEFINITION
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'billing',
]

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
                'billing.context_processors.unread_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'sysnet_core.wsgi.application'


# DATABASE
# SQLite for development; set DATABASE_URL (postgres://...) in production.
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(os.environ['DATABASE_URL'], conn_max_age=600, ssl_require=env_bool('PGSSLMODE_REQUIRE', False))}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'data' / 'db.sqlite3',
            'CONN_MAX_AGE': 60,
        }
    }


# AUTH
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_REDIRECT_URL = '/billing/'
LOGOUT_REDIRECT_URL = '/'


# I18N
LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', 'Africa/Nairobi')
USE_I18N = True
USE_TZ = True


# STATIC & MEDIA
STATIC_URL = 'static/'
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


# FILE UPLOADS
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# DEFAULTS
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
