"""Celery tasks for the project-ingestion pipeline."""
from __future__ import annotations

import logging
import traceback

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_ingestion_job(job_id: str) -> str:
    """Run the ingestor for a :class:`ProjectIngestionJob` and store the result."""
    # Imported lazily to avoid Django app-registry issues at worker import time.
    from .models import ProjectIngestionJob
    from .pipeline import run_ingestion

    try:
        job = ProjectIngestionJob.objects.get(pk=job_id)
    except ProjectIngestionJob.DoesNotExist:
        return f"Job {job_id} not found"

    job.status = ProjectIngestionJob.Status.RUNNING
    job.error = ""
    job.save(update_fields=["status", "error", "updated_at"])

    try:
        result = run_ingestion(
            source_type=job.source_type,
            source_url=job.source_url,
            file_field=job.source_file if job.source_file else None,
        )
        job.result_json = result.to_dict()
        job.status = ProjectIngestionJob.Status.READY
        job.save(update_fields=["result_json", "status", "updated_at"])
        return f"Job {job_id} ready"
    except Exception as exc:  # noqa: BLE001 - record any failure
        logger.exception("Ingestion job %s failed", job_id)
        job.error = f"{exc}\n{traceback.format_exc()}"[:5000]
        job.status = ProjectIngestionJob.Status.FAILED
        job.save(update_fields=["error", "status", "updated_at"])
        return f"Job {job_id} failed: {exc}"
