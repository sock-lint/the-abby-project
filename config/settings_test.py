"""Test-only settings — inherits main settings, swaps infra for in-memory.

Used when running the Django test suite outside Docker (e.g. a local
Windows dev box without Redis running). Docker/CI can still run with
the main settings because the services are actually there.

Usage::

    python manage.py test --settings=config.settings_test apps.rpg
"""
from .settings import *  # noqa: F401,F403

# LocMem cache bypasses Redis — many signal paths call into cache for
# debouncing + pub/sub.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    },
}

# Celery runs synchronously inside the test process — no broker needed.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Eliminate tests accidentally connecting to the real broker on Redis
# if any code path bypasses CELERY_TASK_ALWAYS_EAGER.
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
