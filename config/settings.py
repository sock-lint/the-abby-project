import os
import sys
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
    # Local apps — accounts first (owns AUTH_USER_MODEL)
    "apps.accounts",
    "apps.projects",
    "apps.notifications",
    "apps.ingestion",
    "apps.timecards",
    "apps.payments",
    "apps.achievements",
    "apps.portfolio",
    "apps.rewards",
    "apps.chores",
    "apps.chronicle",
    "apps.homework",
    "apps.mcp_server",
    "apps.google_integration",
    "apps.rpg",
    "apps.habits",
    "apps.pets",
    "apps.quests",
    "apps.activity",
]

# --- MCP server -----------------------------------------------------------
# Exposed via ``python manage.py runmcp`` and the ``mcp`` compose service.
# Values are read by ``apps.mcp_server.server``.
MCP_SERVER_NAME = "abby"
MCP_PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "")
# Allow --as-user pinning only outside production.
MCP_DEV_ALLOW_USER_PIN = DEBUG

# DNS rebinding protection for the MCP Streamable HTTP transport.
#
# The MCP SDK (>=1.9) ships ``TransportSecurityMiddleware`` which rejects any
# request whose ``Host`` header is not in ``allowed_hosts`` (returns HTTP 421
# "Misdirected Request"). If no ``transport_security`` is passed to
# ``FastMCP(...)``, the SDK auto-enables protection with loopback-only hosts,
# which breaks every request reaching the server through a reverse proxy.
#
# ``MCP_ALLOWED_HOSTS`` / ``MCP_ALLOWED_ORIGINS`` accept a comma-separated
# env override. When unset, we derive sensible defaults from Django's
# ``ALLOWED_HOSTS`` + ``CSRF_TRUSTED_ORIGINS`` so a site whose public
# hostname is already listed there "just works" without a second env var.
# Setting either value to ``*`` disables DNS rebinding protection entirely
# (escape hatch — not recommended for production).
def _expand_mcp_host(host: str) -> list[str]:
    """Return ``[host, host:*]`` — matches both default-port and any-port."""
    host = host.strip()
    # Django wildcards like ``.sslip.io`` and ``*`` can't be expressed in the
    # MCP SDK's simple host match, so skip them. Operators who need those
    # should set ``MCP_ALLOWED_HOSTS`` explicitly.
    if not host or host == "*" or host.startswith("."):
        return []
    if ":" in host:
        return [host]
    return [host, f"{host}:*"]


_mcp_allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
if _mcp_allowed_hosts_env:
    MCP_ALLOWED_HOSTS = [
        h.strip() for h in _mcp_allowed_hosts_env.split(",") if h.strip()
    ]
else:
    MCP_ALLOWED_HOSTS = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]
    for _h in ALLOWED_HOSTS:
        for _entry in _expand_mcp_host(_h):
            if _entry not in MCP_ALLOWED_HOSTS:
                MCP_ALLOWED_HOSTS.append(_entry)

_mcp_allowed_origins_env = os.environ.get("MCP_ALLOWED_ORIGINS", "").strip()
if _mcp_allowed_origins_env:
    MCP_ALLOWED_ORIGINS = [
        o.strip() for o in _mcp_allowed_origins_env.split(",") if o.strip()
    ]
else:
    MCP_ALLOWED_ORIGINS = [
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://localhost",
        "http://localhost:*",
        "http://[::1]",
        "http://[::1]:*",
    ]
    for _h in ALLOWED_HOSTS:
        for _entry in _expand_mcp_host(_h):
            for _scheme in ("http", "https"):
                _origin = f"{_scheme}://{_entry}"
                if _origin not in MCP_ALLOWED_ORIGINS:
                    MCP_ALLOWED_ORIGINS.append(_origin)
    # Preserve any explicit CSRF_TRUSTED_ORIGINS (they already include scheme).
    for _origin in CSRF_TRUSTED_ORIGINS:
        if _origin and _origin not in MCP_ALLOWED_ORIGINS:
            MCP_ALLOWED_ORIGINS.append(_origin)

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
# How many Coins a child receives per $1.00 exchanged (money → coins).
COINS_PER_DOLLAR = 10
# Coins granted on a child's birthday, multiplied by age in years (tunable).
BIRTHDAY_COINS_PER_YEAR = 100

# --- Homework timeliness ----------------------------------------------------
# Homework pays no money and no coins — rewards are XP, drops, streaks, and
# quest progress only. The label from ``HomeworkService.get_timeliness`` is
# recorded on each submission and gates the "on_time" quest filter; past
# this many days late the submission flips to ``beyond_cutoff`` instead of
# ``late`` so badges and UI can show the right state.
HOMEWORK_LATE_CUTOFF_DAYS = 3

# --- Anthropic / Claude ---------------------------------------------------
# Optional. When set, enables Claude-powered ingestion enrichment and
# project suggestion flows. Both call sites should import these names
# from django.conf.settings (never re-read os.environ).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# --- Google Gemini (sprite generation) ------------------------------------
# Optional. When set, enables the ``generate_sprite_sheet`` MCP tool which
# calls Gemini 3 Pro Image ("Nano Banana Pro") to produce pixel-art sprite
# sheets from a text prompt. Empty disables the tool (raises at call time).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
# Hard cap on per-call frame count — bounds worst-case API spend per
# invocation (each frame is one image-generation call).
SPRITE_GENERATION_MAX_FRAMES = 8

# --- Google OAuth / Calendar ------------------------------------------------
# Optional. When set, enables "Sign in with Google" and Google Calendar sync.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
    "config.middleware.NoCacheAPIMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.SentryUserMiddleware",
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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "frontend_dist"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    # Sprites: dedicated public-read bucket on Ceph with long-lived Cache-Control
    # headers so browsers cache aggressively and no presigning is needed.
    # Defaults to FileSystemStorage in dev/test; flips to S3 when USE_S3_STORAGE=true.
    "sprites": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

# Media files
#
# Default: local FileSystemStorage at MEDIA_ROOT, served by config/urls.py.
# Production: set USE_S3_STORAGE=true to route every FileField/ImageField
# through django-storages' S3 backend pointed at MinIO (s3.neato.digital).
# When S3 is on, MEDIA_URL/MEDIA_ROOT are ignored and image URLs returned
# in API responses are presigned (signed with AWS_ACCESS_KEY_ID, expire
# after AWS_QUERYSTRING_EXPIRE seconds).

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

USE_S3_STORAGE = os.environ.get("USE_S3_STORAGE", "False").lower() in (
    "true",
    "1",
    "yes",
)

if USE_S3_STORAGE:
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    # boto3 requires a region even when MinIO ignores it.
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    # MinIO needs path-style addressing (bucket-as-subdomain doesn't work
    # against most self-hosted S3-compatible servers behind a reverse proxy).
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    # Presigned URLs — bucket is private, every read goes through a signed URL.
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = int(os.environ.get("AWS_QUERYSTRING_EXPIRE", "3600"))
    # Don't overwrite same-named uploads — django-storages appends a random
    # suffix (e.g. cover_aB12cD.jpg) so two kids uploading "cover.jpg" stay
    # distinct. Mirrors the FileSystemStorage default behavior.
    AWS_S3_FILE_OVERWRITE = False
    # MinIO doesn't honor canned ACLs the same way AWS does; leave unset.
    AWS_DEFAULT_ACL = None

    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}

    # Sprite bucket — public-read, immutable cache, no presigning.
    STORAGES["sprites"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.environ.get("SPRITE_S3_BUCKET", "abby-sprites"),
            # AWS_S3_ENDPOINT_URL is defined earlier in this USE_S3_STORAGE block.
            "endpoint_url": os.environ.get(
                "SPRITE_S3_ENDPOINT", AWS_S3_ENDPOINT_URL,
            ),
            "access_key": AWS_ACCESS_KEY_ID,
            "secret_key": AWS_SECRET_ACCESS_KEY,
            "region_name": AWS_S3_REGION_NAME,
            "addressing_style": "path",
            "signature_version": "s3v4",
            "querystring_auth": False,   # public URLs, no presigning
            "default_acl": "public-read",
            # intentional: True is safe because every write path goes through
            # apps/rpg/sprite_authoring.py which names files as <slug>-<sha256[:8]>.png.
            # Different bytes → different hash → different file (no collision).
            # Identical bytes → same hash → same file (overwrite is a no-op).
            "file_overwrite": True,
            "object_parameters": {
                "CacheControl": "public, max-age=31536000, immutable",
            },
            "custom_domain": os.environ.get("SPRITE_S3_CUSTOM_DOMAIN") or None,
        },
    }

# Allow larger bodies for PDF ingestion and photo uploads now that gunicorn
# handles uploads directly (no nginx in front).
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # 25 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # 25 MB

# Default primary key field type

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model

AUTH_USER_MODEL = "accounts.User"

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
    "daily-reminders": {
        "task": "apps.google_integration.tasks.send_daily_reminders_task",
        # 7:00 AM daily — just after quiet hours end.
        "schedule": crontab(hour=7, minute=0),
    },
    "rpg-perfect-day": {
        "task": "apps.rpg.tasks.evaluate_perfect_day_task",
        "schedule": crontab(hour=23, minute=55),
    },
    "habit-decay": {
        "task": "apps.habits.tasks.decay_habit_strength_task",
        "schedule": crontab(hour=0, minute=5),
    },
    "quest-expire": {
        "task": "apps.quests.tasks.expire_quests_task",
        "schedule": crontab(hour=0, minute=10),
    },
    "quest-boss-rage": {
        "task": "apps.quests.tasks.apply_boss_rage_task",
        "schedule": crontab(hour=0, minute=15),
    },
    "chronicle-birthday-check": {
        "task": "apps.chronicle.tasks.chronicle_birthday_check",
        "schedule": crontab(hour=0, minute=20),
    },
    "chronicle-chapter-transition": {
        "task": "apps.chronicle.tasks.chronicle_chapter_transition",
        "schedule": crontab(hour=0, minute=25),
    },
    "daily-challenge-rotation": {
        "task": "apps.quests.tasks.rotate_daily_challenges_task",
        "schedule": crontab(hour=0, minute=30),
    },
}

# Session

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Email (console backend for development)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@summerforge.local"

# ──────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────
LOG_JSON = os.environ.get("LOG_JSON", "").lower() in ("1", "true", "yes")
_DEFAULT_FORMATTER = "json" if LOG_JSON else "verbose"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "json": {
            "()": "config.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _DEFAULT_FORMATTER,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ──────────────────────────────────────────────────────────────────────────
# Sentry error tracking
# ──────────────────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.environ.get(
    "SENTRY_ENVIRONMENT", "development" if DEBUG else "production"
)
SENTRY_TRACES_SAMPLE_RATE = float(
    os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.2")
)

if SENTRY_DSN:
    import logging as _logging

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=True,
        release=os.environ.get("SENTRY_RELEASE", None),
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            LoggingIntegration(
                level=_logging.WARNING,
                event_level=_logging.ERROR,
            ),
            RedisIntegration(),
        ],
    )

# ──────────────────────────────────────────────────────────────────────────
# Testing — skip migrations and use syncdb for test databases.
#
# The AUTH_USER_MODEL move from projects.User → accounts.User left the
# migration graph with unresolvable settings.AUTH_USER_MODEL FK references
# on fresh databases. Production is unaffected (migrations were applied
# sequentially). For test databases, bypass the migration graph entirely
# and create tables from current model state.
# ──────────────────────────────────────────────────────────────────────────
if "test" in sys.argv:
    MIGRATION_MODULES = {app.split(".")[-1]: None for app in INSTALLED_APPS}
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # Tests use SimpleUploadedFile against a local temp dir — never reach for
    # MinIO even when USE_S3_STORAGE is set in the developer's shell env.
    USE_S3_STORAGE = False
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    STORAGES["sprites"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
