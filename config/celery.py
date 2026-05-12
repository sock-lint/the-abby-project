import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("summerforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

from config.logging import register_celery_failure_handler  # noqa: E402

register_celery_failure_handler()


# Django's request handler calls close_old_connections() between requests
# automatically; Celery tasks don't. Without these hooks, worker processes
# hold DB connections past CONN_MAX_AGE and accumulate stale slots over time
# — the canonical Celery/Django integration recipe.
@task_prerun.connect
def _close_stale_db_connections_before_task(*args, **kwargs):
    from django.db import close_old_connections

    close_old_connections()


@task_postrun.connect
def _close_stale_db_connections_after_task(*args, **kwargs):
    from django.db import close_old_connections

    close_old_connections()
