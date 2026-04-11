import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-dev-key-change-me-in-production"
)

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Honor X-Forwarded-Proto from Traefik/Caddy so Django knows requests are HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_celery_beat",
    # Local apps
    "apps.projects",
    "apps.timecards",
    "apps.payments",
    "apps.achievements",
    "apps.portfolio",
    "apps.rewards",
    "apps.mcp_server",
]

# --- MCP server -----------------------------------------------------------
# Exposed via ``python manage.py runmcp`` and the ``mcp`` compose service.
# Values are read by ``apps.mcp_server.server``.
MCP_SERVER_NAME = "abby"
MCP_PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "")
# Allow --as-user pinning only outside production.
MCP_DEV_ALLOW_USER_PIN = DEBUG

# --- Rewards / Coins economy ----------------------------------------------
# How many Coins a child earns per hour of tracked time.
COINS_PER_HOUR = 5
# Per-rarity coin bonus when a Badge is earned.
COINS_PER_BADGE_RARITY = {
    "common": 5,
    "uncommon": 15,
    "rare": 35,
    "epic": 75,
    "legendary": 150,
}

# --- Anthropic / Claude ---------------------------------------------------
# Optional. When set, enables Claude-powered ingestion enrichment and
# project suggestion flows. Both call sites should import these names
# from django.conf.settings (never re-read os.environ).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///db.sqlite3",
        conn_max_age=600,
    )
}

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Phoenix"
USE_I18N = True
USE_TZ = True

# Static files
#
# The React bundle is built into /app/frontend_dist by the Docker build
# and picked up here so collectstatic copies it into STATIC_ROOT. Vite
# already content-hashes filenames, so we use CompressedStaticFilesStorage
# (no Manifest layer) — WhiteNoise gzips/brotlis at collectstatic time and
# serves Vite's original hashed filenames directly.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "frontend_dist"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Media files

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Allow larger bodies for PDF ingestion and photo uploads now that gunicorn
# handles uploads directly (no nginx in front).
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # 25 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # 25 MB

# Default primary key field type

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model

AUTH_USER_MODEL = "projects.User"

# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# CORS
#
# In production the React bundle is served by Django from the same origin as
# the API, so no cross-origin requests happen. These defaults exist only for
# the local Vite dev server (npm run dev at :3000 / :5173) which proxies /api
# to the Django dev server on :8000.

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
CORS_ALLOW_CREDENTIALS = True

# Cache (Redis)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Celery

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "auto-clock-out": {
        "task": "apps.timecards.tasks.auto_clock_out_task",
        "schedule": crontab(minute="*/30"),
    },
    "weekly-timecards": {
        "task": "apps.timecards.tasks.generate_weekly_timecards_task",
        # Sunday 23:55 local — runs at the end of the just-finished week.
        "schedule": crontab(hour=23, minute=55, day_of_week="sun"),
    },
    "weekly-email-summaries": {
        "task": "apps.timecards.tasks.send_weekly_email_summaries",
        "schedule": crontab(hour=8, minute=0, day_of_week="sun"),
    },
}

# Session

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Email (console backend for development)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@summerforge.local"
