"""Ingestion job MCP tools.

Wraps the Scrapy-style project ingestion pipeline. All tools are parent-only.
PDF file uploads are not supported over MCP — use URL sources only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.ingestion.models import ProjectIngestionJob
from apps.projects.models import (
    MaterialItem,
    Project,
    ProjectMilestone,
)
from apps.achievements.models import SkillCategory

from ..context import require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    CommitIngestionJobIn,
    GetIngestionJobIn,
    ListIngestionJobsIn,
    SubmitIngestionJobIn,
)
from ..server import tool
from ..shapes import ingestion_job_to_dict, project_detail_to_dict


@tool()
@safe_tool
def submit_ingestion_job(params: SubmitIngestionJobIn) -> dict[str, Any]:
    """Create an ingestion job for an Instructables/URL source and enqueue it.

    Parent-only. PDF uploads are not available via MCP. The Celery
    ``run_ingestion_job`` task runs the matching ingestor and stores the
    normalized draft in ``result_json``; poll with ``get_ingestion_job``.
    """
    parent = require_parent()

    if params.source_type == "pdf":
        raise MCPValidationError(
            "PDF uploads are not supported over MCP. Use the web UI.",
        )
    if not params.source_url:
        raise MCPValidationError("source_url is required.")

    job = ProjectIngestionJob.objects.create(
        created_by=parent,
        source_type=params.source_type,
        source_url=params.source_url,
    )

    # Enqueue via Celery; fall back to inline execution if the broker is down.
    from apps.ingestion.tasks import run_ingestion_job

    try:
        run_ingestion_job.delay(str(job.id))
    except Exception:  # noqa: BLE001 - broker may be unavailable in dev
        run_ingestion_job(str(job.id))

    job.refresh_from_db()
    return ingestion_job_to_dict(job)


@tool()
@safe_tool
def get_ingestion_job(params: GetIngestionJobIn) -> dict[str, Any]:
    """Fetch a single ingestion job by UUID (parent-only)."""
    parent = require_parent()
    try:
        job = ProjectIngestionJob.objects.get(pk=params.job_id, created_by=parent)
    except ProjectIngestionJob.DoesNotExist:
        raise MCPNotFoundError(f"Ingestion job {params.job_id} not found.")
    return ingestion_job_to_dict(job)


@tool()
@safe_tool
def list_ingestion_jobs(params: ListIngestionJobsIn) -> dict[str, Any]:
    """List the current parent's recent ingestion jobs."""
    parent = require_parent()
    qs = ProjectIngestionJob.objects.filter(created_by=parent)
    if params.status:
        qs = qs.filter(status=params.status)
    qs = qs.order_by("-created_at")[: params.limit]
    return {"jobs": [ingestion_job_to_dict(j) for j in qs]}


@tool()
@safe_tool
def commit_ingestion_job(params: CommitIngestionJobIn) -> dict[str, Any]:
    """Materialize a staged ingestion job into a real Project (parent-only).

    Mirrors the existing ``ProjectIngestViewSet.commit`` action — reads the
    staged ``result_json``, applies optional overrides, creates the Project
    + milestones + materials in a single transaction, and marks the job
    ``committed``.
    """
    parent = require_parent()
    from apps.ingestion.pipeline.base import IngestionResult
    from apps.ingestion.pipeline.category import resolve_category_id

    try:
        job = ProjectIngestionJob.objects.get(pk=params.job_id, created_by=parent)
    except ProjectIngestionJob.DoesNotExist:
        raise MCPNotFoundError(f"Ingestion job {params.job_id} not found.")

    if job.status != ProjectIngestionJob.Status.READY:
        raise MCPValidationError(
            f"Ingestion job is {job.status}, not ready to commit.",
        )
    if not job.result_json:
        raise MCPValidationError("Ingestion job has no staged result.")

    staged = IngestionResult.from_dict(job.result_json)

    category_id = params.category_id
    if category_id is None:
        category_id = resolve_category_id(staged.category_hint)

    assigned_to = None
    if params.assigned_to_id is not None:
        # Cross-family safety: only commit to a child in this parent's
        # family. resolve_target_user raises MCPNotFoundError on miss /
        # cross-family without leaking existence.
        assigned_to = resolve_target_user(parent, params.assigned_to_id)

    category = None
    if category_id is not None:
        try:
            category = SkillCategory.objects.get(pk=category_id)
        except SkillCategory.DoesNotExist:
            category = None

    with transaction.atomic():
        project = Project.objects.create(
            title=params.title or staged.title or "Untitled Project",
            description=params.description
            if params.description is not None else staged.description,
            instructables_url=(
                staged.source_url if staged.source_type == "instructables" else None
            ),
            difficulty=int(params.difficulty or staged.difficulty_hint or 2),
            category=category,
            assigned_to=assigned_to,
            created_by=parent,
            bonus_amount=params.bonus_amount or Decimal("0.00"),
            materials_budget=params.materials_budget or Decimal("0.00"),
            due_date=params.due_date,
            status="active",
        )

        ProjectMilestone.objects.bulk_create([
            ProjectMilestone(
                project=project,
                title=(m.title or "")[:200] or f"Step {i + 1}",
                description=m.description or "",
                order=m.order or i,
            )
            for i, m in enumerate(staged.milestones)
        ])

        material_rows = []
        for m in staged.materials:
            raw_cost = m.estimated_cost
            try:
                cost = Decimal(str(raw_cost)) if raw_cost not in (None, "") else Decimal("0.00")
            except Exception:  # noqa: BLE001
                cost = Decimal("0.00")
            material_rows.append(MaterialItem(
                project=project,
                name=(m.name or "")[:200],
                description=m.description or "",
                estimated_cost=cost,
            ))
        MaterialItem.objects.bulk_create(material_rows)

        job.project = project
        job.status = ProjectIngestionJob.Status.COMMITTED
        job.save(update_fields=["project", "status", "updated_at"])

    project.refresh_from_db()
    return project_detail_to_dict(project)
