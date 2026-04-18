import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("summerforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

from config.logging import register_celery_failure_handler  # noqa: E402

register_celery_failure_handler()
