"""Celery tasks for the project-ingestion pipeline."""
from __future__ import annotations

import logging
import traceback

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def run_ingestion_job(job_id: str) -> str:
    """Run the ingestor for a :class:`ProjectIngestionJob` and store the result."""
    # Imported lazily to avoid Django app-registry issues at worker import time.
    from .models import ProjectIngestionJob
    from .pipeline import run_ingestion

    jobs = ProjectIngestionJob.objects.filter(pk=job_id)
    claimed = jobs.filter(
        status__in=[ProjectIngestionJob.Status.PENDING, ProjectIngestionJob.Status.FAILED],
        project__isnull=True,
    ).update(status=ProjectIngestionJob.Status.RUNNING, error="", updated_at=timezone.now())
    if not claimed:
        current = jobs.values_list("status", flat=True).first()
        return f"Job {job_id} not found" if current is None else f"Job {job_id} skipped ({current})"

    running = jobs.filter(status=ProjectIngestionJob.Status.RUNNING, project__isnull=True)
    job = running.first()
    if job is None:
        return f"Job {job_id} skipped (state changed)"

    try:
        result = run_ingestion(
            source_type=job.source_type,
            source_url=job.source_url,
            file_field=job.source_file if job.source_file else None,
        )
        finished = running.update(
            result_json=result.to_dict(), status=ProjectIngestionJob.Status.READY, updated_at=timezone.now(),
        )
        if not finished:
            return f"Job {job_id} skipped (state changed)"
        return f"Job {job_id} ready"
    except Exception as exc:  # noqa: BLE001 - record any failure
        logger.exception("Ingestion job %s failed", job_id)
        finished = running.update(
            error=f"{exc}\n{traceback.format_exc()}"[:5000],
            status=ProjectIngestionJob.Status.FAILED, updated_at=timezone.now(),
        )
        if not finished:
            return f"Job {job_id} skipped (state changed)"
        return f"Job {job_id} failed: {exc}"
