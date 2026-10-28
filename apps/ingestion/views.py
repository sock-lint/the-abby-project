"""Ingestion staging flow viewset.

Handles the submit → poll → commit lifecycle for URL/PDF imports. The
heavy lifting lives in ``apps.ingestion.pipeline`` (runner.py and the
per-source ingestors); this viewset wires HTTP to that pipeline plus
the ``Project``/``ProjectMilestone``/``MaterialItem``/``ProjectStep``/
``ProjectResource`` creation on commit.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.google_integration.drive import GoogleDriveSelectionSerializer, GoogleDriveService
from apps.projects.models import (
    MaterialItem, ProjectMilestone, ProjectResource, ProjectStep,
)
from apps.projects.serializers import ProjectDetailSerializer
from config.permissions import IsParent
from config.participation import is_personal_space

from .models import ProjectIngestionJob
from .pipeline.base import IngestionResult
from .pipeline.category import resolve_category_id
from .serializers import ProjectIngestionJobSerializer

logger = logging.getLogger(__name__)


class ProjectIngestViewSet(viewsets.ModelViewSet):
    """Staging flow for auto-ingested projects.

    POST   /projects/ingest/             -> create job + enqueue Celery task
    GET    /projects/ingest/{id}/        -> poll status / read staged result
    PATCH  /projects/ingest/{id}/        -> parent edits the staged result_json
    POST   /projects/ingest/{id}/commit/ -> materialize Project + milestones + materials
    DELETE /projects/ingest/{id}/        -> mark discarded
    """

    serializer_class = ProjectIngestionJobSerializer
    permission_classes = [IsParent]

    def get_queryset(self):
        return ProjectIngestionJob.objects.filter(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        source_type = request.data.get("source_type") or "url"
        source_url = request.data.get("source_url") or None
        source_file = request.FILES.get("source_file")

        if source_type == "pdf" and not source_file:
            return Response(
                {"error": "source_file required for pdf ingestion"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if source_type != "pdf" and not source_url:
            return Response(
                {"error": "source_url required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = ProjectIngestionJob.objects.create(
            created_by=request.user,
            source_type=source_type,
            source_url=source_url,
            source_file=source_file,
        )

        return self._start_job(job)

    @action(detail=False, methods=["post"], url_path="google-drive")
    def google_drive(self, request):
        """Copy a selected Drive PDF before starting the ordinary staging flow."""
        selection = GoogleDriveSelectionSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        GoogleDriveService.require_configured()
        resource, copied_file = GoogleDriveService.download_pdf(**selection.validated_data)
        with copied_file:
            job = ProjectIngestionJob.objects.create(
                created_by=request.user,
                source_type=ProjectIngestionJob.SourceType.PDF,
                source_url=resource["url"],
                source_file=copied_file,
            )
        return self._start_job(job)

    @staticmethod
    def _start_job(job):
        # Enqueue via Celery; fall back to inline execution if the broker
        # is unavailable (e.g. local dev without a worker running).
        from .tasks import run_ingestion_job
        try:
            run_ingestion_job.delay(str(job.id))
        except Exception:  # noqa: BLE001 - broker may be down in dev
            logger.warning("Celery broker unavailable, running ingestion inline", exc_info=True)
            run_ingestion_job(str(job.id))

        return Response(
            ProjectIngestionJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        job = self.get_object()
        # Serializer.save() writes the instance's lifecycle fields as well
        # as edited fields. Construct it only after locking a fresh snapshot
        # so a stale PATCH cannot reopen a committed/discarded job.
        job = get_object_or_404(self.get_queryset().select_for_update(), pk=job.pk)
        if job.status != ProjectIngestionJob.Status.READY:
            return Response(
                {"error": f"This import cannot be edited while it is {job.status}."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(job, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        job = self.get_queryset().select_for_update().get(pk=job.pk)
        if job.status == ProjectIngestionJob.Status.COMMITTED:
            return Response(
                {"error": "This import has already created a project."},
                status=status.HTTP_409_CONFLICT,
            )
        job.status = ProjectIngestionJob.Status.DISCARDED
        job.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def commit(self, request, pk=None):
        """Create the real Project from the (possibly edited) staged result."""
        job = self.get_object()
        # Re-read under the owner-scoped lock before checking status. A second
        # tab or a retry after an interrupted response must reuse the project.
        job = self.get_queryset().select_for_update().get(pk=job.pk)
        if job.status == ProjectIngestionJob.Status.COMMITTED:
            if job.project_id is None:
                return Response(
                    {"error": "The project created by this import has been deleted."},
                    status=status.HTTP_409_CONFLICT,
                )
            if is_personal_space(request) and job.project.assigned_to_id != request.user.pk:
                raise NotFound()
            return Response(ProjectDetailSerializer(job.project).data)
        if job.status != ProjectIngestionJob.Status.READY:
            return Response(
                {"error": f"job is {job.status}, not ready"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not job.result_json:
            return Response(
                {"error": "no staged result"}, status=status.HTTP_400_BAD_REQUEST
            )

        staged = IngestionResult.from_dict(job.result_json)

        # Overrides from request body let the frontend preview pass final values
        # (category_id, difficulty, assigned_to_id, bonus/budget) that don't
        # live on the ingestion result itself.
        overrides = request.data or {}

        category_id = overrides.get("category_id")
        if category_id is None:
            category_id = resolve_category_id(staged.category_hint)

        payload = {
            "title": overrides.get("title") or staged.title or "Untitled Project",
            "description": overrides.get("description", staged.description),
            "instructables_url": staged.source_url if staged.source_type == "instructables" else None,
            "difficulty": int(overrides.get("difficulty") or staged.difficulty_hint or 2),
            "category_id": category_id,
            "assigned_to_id": overrides.get("assigned_to_id"),
            "bonus_amount": overrides.get("bonus_amount", "0.00"),
            "materials_budget": overrides.get("materials_budget", "0.00"),
            "due_date": overrides.get("due_date") or None,
        }

        with transaction.atomic():
            # Pass request context so ProjectDetailSerializer's family-scoping
            # validator on assigned_to_id can read request.user.family.
            serializer = ProjectDetailSerializer(
                data=payload, context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            extras = {"created_by": request.user}
            if is_personal_space(request):
                extras.update(assigned_to=request.user, bonus_amount=0, hourly_rate_override=0,
                              hourly_rate_is_personal_default=True)
            project = serializer.save(**extras)

            # Milestones: ingestors no longer populate these by default
            # (walkthrough content now lives on ``steps``). Parents can still
            # override with an explicit milestones list from the preview. We
            # use a loop instead of bulk_create so we get pks back on every
            # backend (SQLite included) and can resolve ``milestone_index``
            # on each step below.
            milestones = overrides.get("milestones") or []
            created_milestones: list[ProjectMilestone] = []
            for i, m in enumerate(milestones):
                created_milestones.append(ProjectMilestone.objects.create(
                    project=project,
                    title=(m.get("title") or "")[:200] or f"Milestone {i + 1}",
                    description=m.get("description") or "",
                    order=m.get("order", i),
                ))

            materials = overrides.get("materials")
            if materials is None:
                materials = [m.to_dict() for m in staged.materials]
            material_rows = []
            for m in materials:
                raw_cost = m.get("estimated_cost")
                try:
                    cost = Decimal(str(raw_cost)) if raw_cost not in (None, "") else Decimal("0.00")
                except (InvalidOperation, TypeError):
                    cost = Decimal("0.00")
                material_rows.append(MaterialItem(
                    project=project,
                    name=(m.get("name") or "")[:200],
                    description=m.get("description") or "",
                    estimated_cost=cost,
                ))
            MaterialItem.objects.bulk_create(material_rows)

            # Steps — the real home for walkthrough content going forward.
            # ``milestone_index`` (when present) is a 0-based index into the
            # milestones list above; out-of-range or missing values fall back
            # to a "loose" (unassigned) step rather than raising.
            steps_input = overrides.get("steps")
            if steps_input is None:
                steps_input = [s.to_dict() for s in staged.steps]
            created_steps = []
            for i, s in enumerate(steps_input):
                ms_idx = s.get("milestone_index")
                step_milestone = None
                if isinstance(ms_idx, int) and 0 <= ms_idx < len(created_milestones):
                    step_milestone = created_milestones[ms_idx]
                created_steps.append(ProjectStep.objects.create(
                    project=project,
                    milestone=step_milestone,
                    title=(s.get("title") or "")[:200] or f"Step {i + 1}",
                    description=s.get("description") or "",
                    order=s.get("order", i),
                ))

            # Resources — resolve optional step_index to the just-created step pk.
            resources_input = overrides.get("resources")
            if resources_input is None:
                resources_input = [r.to_dict() for r in staged.resources]
            for r_idx, res in enumerate(resources_input):
                step_index = res.get("step_index")
                step_fk = None
                if step_index is not None and isinstance(step_index, int) and (
                    0 <= step_index < len(created_steps)
                ):
                    step_fk = created_steps[step_index]
                url = (res.get("url") or "").strip()
                if not url:
                    continue
                ProjectResource.objects.create(
                    project=project,
                    step=step_fk,
                    title=(res.get("title") or "")[:200],
                    url=url[:1000],
                    resource_type=res.get("resource_type") or ProjectResource.ResourceType.LINK,
                    order=res.get("order", r_idx),
                )

            job.project = project
            job.status = ProjectIngestionJob.Status.COMMITTED
            job.save(update_fields=["project", "status", "updated_at"])

        return Response(
            ProjectDetailSerializer(project).data,
            status=status.HTTP_201_CREATED,
        )
