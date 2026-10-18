"""Periodic bounded draining of the database's private-media deletion outbox."""
import logging

from celery import shared_task

from .file_cleanup import process_pending_file_deletions

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=60, time_limit=75)
def cleanup_deleted_files():
    result = process_pending_file_deletions()
    if any(result.values()):
        log = logger.warning if result["failed"] else logger.info
        log(
            "Private file cleanup: deleted=%s failed=%s referenced=%s",
            result["deleted"], result["failed"], result["referenced"],
        )
    return result
