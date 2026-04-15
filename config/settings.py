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
    "apps.homework",
    "apps.mcp_server",
    "apps.google_integration",
    "apps.rpg",
    "apps.habits",
    "apps.pets",
    "apps.quests",
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

# --- Homework reward scaling ------------------------------------------------
from decimal import Decimal as _D  # noqa: E402

HOMEWORK_EFFORT_MULTIPLIERS = {1: _D("0.5"), 2: _D("0.75"), 3: _D("1.0"), 4: _D("1.5"), 5: _D("2.0")}
HOMEWORK_EARLY_BONUS = _D("1.25")
HOMEWORK_ON_TIME_MULTIPLIER = _D("1.0")
HOMEWORK_LATE_PENALTY = _D("0.5")
HOMEWORK_LATE_CUTOFF_DAYS = 3  # 0 rewards beyond this many days late

# --- Anthropic / Claude ---------------------------------------------------
# Optional. When set, enables Claude-powered ingestion enrichment and
# project suggestion flows. Both call sites should import these names
# from django.conf.settings (never re-read os.environ).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# --- Google OAuth / Calendar ------------------------------------------------
# Optional. When set, enables "Sign in with Google" and Google Calendar sync.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
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
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
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
