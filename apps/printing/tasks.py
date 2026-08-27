"""Celery tasks for the Forge.

Nothing here talks to a printer. The MQTT connection lives in exactly one
place — the ``run_printer_listener`` process — because the X1's broker
tolerates only about four clients and a Celery worker pool would blow past
that. See ``apps/printing/fanout.py``.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlparse

from celery import shared_task
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Cap on a cached thumbnail. Model-host og:images are typically < 500 KB;
#: anything larger is not a thumbnail and we keep the remote URL instead.
MAX_THUMBNAIL_BYTES = 3_000_000


@shared_task
def enrich_request_metadata(request_id: int) -> str:
    """Scrape the model link for a real title, author and thumbnail.

    Runs after the child has already submitted, so a slow or unreachable
    model host degrades the card rather than blocking the form. Only fills in
    a title the child didn't type.
    """
    from .metadata import fetch_link_metadata
    from .models import PrintRequest

    try:
        print_request = PrintRequest.objects.get(pk=request_id)
    except PrintRequest.DoesNotExist:
        return f"print request {request_id} is gone"
    if not print_request.source_url:
        return "no source url"

    meta = fetch_link_metadata(print_request.source_url)
    fields = []
    placeholder = print_request.title in ("", "Untitled print")
    if meta.title and (placeholder or not print_request.title):
        print_request.title = meta.title[:160]
        fields.append("title")
    if meta.thumbnail_url and not print_request.thumbnail_url:
        print_request.thumbnail_url = meta.thumbnail_url[:500]
        fields.append("thumbnail_url")
    if meta.author and not print_request.source_author:
        print_request.source_author = meta.author[:120]
        fields.append("source_author")
    if meta.source_kind and print_request.source_kind != meta.source_kind:
        print_request.source_kind = meta.source_kind
        fields.append("source_kind")

    if fields:
        print_request.save(update_fields=[*fields, "updated_at"])
    if print_request.thumbnail_url:
        cache_request_thumbnail.delay(print_request.pk)
    return f"enriched {request_id}: {', '.join(fields) or 'nothing new'}"


@shared_task
def cache_request_thumbnail(request_id: int) -> str:
    """Copy the remote og:image into our own storage.

    Model hosts rotate CDN URLs, so a card that only ever pointed at the
    remote image goes blank weeks later. Best-effort: on any failure the
    remote URL stays as the fallback.
    """
    from config.url_safety import UnsafeURLError, safe_get

    from .models import PrintRequest

    try:
        print_request = PrintRequest.objects.get(pk=request_id)
    except PrintRequest.DoesNotExist:
        return f"print request {request_id} is gone"
    if not print_request.thumbnail_url or print_request.thumbnail:
        return "nothing to cache"

    try:
        response = safe_get(print_request.thumbnail_url, timeout=8)
    except UnsafeURLError as exc:
        logger.info("printing: refused unsafe thumbnail URL for %s: %s", request_id, exc)
        return "unsafe url"
    except Exception as exc:  # noqa: BLE001 - best effort; the remote URL stands
        logger.info("printing: thumbnail fetch failed for %s: %s", request_id, exc)
        return "fetch failed"

    if response.status_code >= 400:
        return f"http {response.status_code}"
    content = response.content or b""
    if not content or len(content) > MAX_THUMBNAIL_BYTES:
        return "not a usable image"
    if "image" not in (response.headers.get("Content-Type") or ""):
        return "not an image"

    name = (urlparse(print_request.thumbnail_url).path.rsplit("/", 1)[-1]
            or "thumb.jpg")[:80]
    print_request.thumbnail.save(
        f"{print_request.pk}-{name}", ContentFile(BytesIO(content).getvalue()),
        save=True,
    )
    return f"cached thumbnail for {request_id}"


@shared_task
def reconcile_stale_jobs() -> str:
    """Close jobs whose printer went quiet, so a request never sticks forever.

    A power cut mid-print leaves an open ``PrintJob`` and a request stuck in
    ``printing``. The listener closes jobs on a ``gcode_state`` transition,
    which never arrives if the printer simply vanished — so this daily sweep
    is the backstop. Such a job closes as ``unknown``, not ``failed``: we
    genuinely don't know whether it finished.
    """
    from .constants import STALE_JOB_MINUTES
    from .models import PrintJob, PrintJobEvent
    from .services import PrintRequestService

    cutoff = timezone.now() - timedelta(minutes=STALE_JOB_MINUTES)
    stale = PrintJob.objects.filter(finished_at__isnull=True).filter(
        # Either its last report is old, or it never reported after starting.
        Q(last_report_at__lt=cutoff)
        | Q(last_report_at__isnull=True, started_at__lt=cutoff),
    )
    closed = 0
    for job in stale:
        job.state = PrintJob.State.UNKNOWN
        job.finished_at = timezone.now()
        job.duration_minutes = max(
            0, int((job.finished_at - job.started_at).total_seconds() // 60),
        )
        job.failure_reason = (
            "The printer stopped reporting, so we don't know how this print ended."
        )
        job.save(update_fields=[
            "state", "finished_at", "duration_minutes", "failure_reason", "updated_at",
        ])
        PrintJobEvent.objects.create(
            job=job,
            kind=PrintJobEvent.Kind.FAILED,
            message=job.failure_reason,
            context={"reason": "stale", "cutoff_minutes": STALE_JOB_MINUTES},
        )
        PrintRequestService.close_out(job)
        closed += 1
    return f"closed {closed} stale print job(s)"
