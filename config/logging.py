"""Logging helpers: a minimal JSON formatter and the Celery task-failure bridge.

Kept dependency-free (no ``python-json-logger``) so the production log
pipeline doesn't grow an extra package for ~30 lines of formatter code.

Activation: set ``LOG_JSON=1`` in the environment. The default formatter
stays plain text so local ``docker compose logs`` output remains readable.
"""
from __future__ import annotations

import json
import logging


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    # Attributes on LogRecord that the stdlib sets; anything else on the record
    # is treated as structured extras and merged into the payload.
    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = repr(value)
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def register_celery_failure_handler() -> None:
    """Log every Celery task failure with structured context.

    Sentry's ``CeleryIntegration`` already captures task exceptions when a
    DSN is configured, but this handler runs unconditionally — so failures
    still show up in JSON logs (aggregator-searchable) even without Sentry,
    and future changes to the Sentry wiring can't silently drop visibility
    into the 9 scheduled tasks in ``CELERY_BEAT_SCHEDULE``.
    """
    from celery.signals import task_failure

    logger = logging.getLogger("celery.task")

    @task_failure.connect
    def _on_task_failure(sender=None, task_id=None, exception=None,
                         args=None, kwargs=None, einfo=None, **_):
        logger.error(
            "celery task failed",
            extra={
                "task_name": getattr(sender, "name", "unknown"),
                "task_id": task_id,
                "exception": repr(exception) if exception else None,
            },
            exc_info=einfo.exc_info if einfo else None,
        )
