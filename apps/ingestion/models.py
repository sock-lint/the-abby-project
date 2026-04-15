import uuid

from django.conf import settings
from django.db import models

from config.base_models import TimestampedModel


class ProjectIngestionJob(TimestampedModel):
    """Staging row for project auto-ingestion from a URL or uploaded file.

    A job is created when a parent submits a source; a Celery task runs
    the matching ingestor and stores the result in ``result_json``. The
    parent then reviews/edits the staged draft and commits it, which
    creates the real ``Project`` row plus its milestones and materials.
    """

    class SourceType(models.TextChoices):
        INSTRUCTABLES = "instructables", "Instructables"
        URL = "url", "Generic URL"
        PDF = "pdf", "PDF Upload"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        DISCARDED = "discarded", "Discarded"
        COMMITTED = "committed", "Committed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="ingestion_jobs",
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_url = models.URLField(blank=True, null=True, max_length=1000)
    source_file = models.FileField(
        upload_to="ingestion/", blank=True, null=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    result_json = models.JSONField(blank=True, null=True)
    error = models.TextField(blank=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingestion_jobs",
    )

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "projects_projectingestionjob"
        ordering = ["-created_at"]

    def __str__(self):
        return f"IngestionJob {self.id} ({self.status})"
