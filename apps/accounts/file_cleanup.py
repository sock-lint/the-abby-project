"""Durable cleanup for deleted private media, including ORM cascades.

Only the default private-media store is covered. Global SpriteAsset artwork
uses its existing separate storage and lifecycle. No storage reads or writes
occur in deletion signals; a committed database outbox is the authority.
"""
from datetime import timedelta
from time import monotonic

from django.apps import apps
from django.core.files.storage import default_storage
from django.db import connections, transaction
from django.db.models import Q
from django.db.models.signals import pre_delete
from django.utils import timezone

from .models import PendingFileDeletion


PRIVATE_FILE_FIELDS = {
    "accounts.User": ("avatar",),
    "projects.Project": ("cover_photo",),
    "projects.MaterialItem": ("receipt_photo",),
    "portfolio.ProjectPhoto": ("image",),
    "homework.HomeworkProof": ("image",),
    "creations.Creation": ("image", "audio"),
    "ingestion.ProjectIngestionJob": ("source_file",),
    "rewards.Reward": ("image",),
    "printing.PrintRequest": ("thumbnail", "model_file"),
}


def _queue_deleted_files(sender, instance, using, **kwargs):
    for field_name in PRIVATE_FILE_FIELDS[sender._meta.label]:
        name = getattr(instance, field_name).name
        if name:
            PendingFileDeletion.objects.using(using).get_or_create(storage_key=name)


def connect_file_cleanup_signals():
    for label in PRIVATE_FILE_FIELDS:
        pre_delete.connect(
            _queue_deleted_files,
            sender=apps.get_model(label),
            dispatch_uid=f"accounts.private-file-cleanup.{label}",
        )


def _still_referenced(storage_key, *, using):
    # File names normally have one owner, but a manually shared/legacy pointer
    # must never cause a surviving family's file to be removed. The pending
    # row remains until its final reference is deleted.
    for label, fields in PRIVATE_FILE_FIELDS.items():
        query = Q()
        for field in fields:
            query |= Q(**{field: storage_key})
        if apps.get_model(label).objects.using(using).filter(query).exists():
            return True
    return False


def process_pending_file_deletions(*, limit=25, using="default", now=None):
    """Attempt a bounded committed batch; retain every uncertain file pointer.

    A storage success followed by process/database failure leaves the outbox
    row retryable. Django's supported filesystem/S3 deletes are idempotent
    when a key is already absent. The queue row lock prevents two workers
    processing the same key together. No caller may run this inside an outer
    transaction, including an eager task inside a request being rolled back.
    """
    connection = connections[using]
    if connection.in_atomic_block:
        raise RuntimeError("File cleanup requires a committed transaction.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100.")
    now = now or timezone.now()
    ids = list(
        PendingFileDeletion.objects.using(using).filter(retry_at__lte=now)
        .order_by("retry_at", "pk").values_list("pk", flat=True)[:limit]
    )
    result = {"deleted": 0, "failed": 0, "referenced": 0}
    started = monotonic()
    for job_id in ids:
        if monotonic() - started >= 45:
            break
        with transaction.atomic(using=using):
            jobs = PendingFileDeletion.objects.using(using).filter(pk=job_id, retry_at__lte=now)
            if connection.features.has_select_for_update_skip_locked:
                jobs = jobs.select_for_update(skip_locked=True)
            else:
                jobs = jobs.select_for_update()
            job = jobs.first()
            if job is None:
                continue
            job.attempts += 1
            job.last_attempt_at = now
            if _still_referenced(job.storage_key, using=using):
                job.last_error = "still_referenced"
                result["referenced"] += 1
            else:
                try:
                    default_storage.delete(job.storage_key)
                except Exception:  # Storage/network errors may contain private names or credentials.
                    job.last_error = "storage_error"
                    result["failed"] += 1
                else:
                    job.delete(using=using)
                    result["deleted"] += 1
                    continue
            delay_minutes = min(60 * 24, 5 * 2 ** min(job.attempts - 1, 9))
            job.retry_at = now + timedelta(minutes=delay_minutes)
            job.save(using=using, update_fields=[
                "attempts", "last_attempt_at", "last_error", "retry_at", "updated_at",
            ])
    return result
