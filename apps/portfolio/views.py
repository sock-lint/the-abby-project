import io
import logging

from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import RoleFilteredQuerySetMixin, filter_queryset_by_role

from .models import ProjectPhoto
from .serializers import ProjectPhotoSerializer

logger = logging.getLogger(__name__)


class ProjectPhotoViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProjectPhotoSerializer
    queryset = ProjectPhoto.objects.select_related("project")
    role_filter_field = "project__assigned_to"

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.role != "parent" and instance.user_id != request.user.id:
            raise PermissionDenied("You can only delete your own photos.")
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PortfolioView(APIView):
    def get(self, request):
        user = request.user

        # Project photos (existing).
        photos = filter_queryset_by_role(
            user,
            ProjectPhoto.objects.select_related("project"),
            role_filter_field="project__assigned_to",
        )

        grouped = {}
        for photo in photos:
            pid = photo.project_id
            if pid not in grouped:
                grouped[pid] = {
                    "project_id": pid,
                    "project_title": photo.project.title,
                    "photos": [],
                }
            grouped[pid]["photos"].append(ProjectPhotoSerializer(photo).data)

        # Homework proofs (approved submissions only).
        from apps.homework.models import HomeworkProof, HomeworkSubmission

        hw_proofs = filter_queryset_by_role(
            user,
            HomeworkProof.objects.filter(
                submission__status=HomeworkSubmission.Status.APPROVED,
            ).select_related("submission__assignment"),
            role_filter_field="submission__user",
        )

        hw_grouped = {}
        for proof in hw_proofs:
            subject = proof.submission.assignment.subject
            if subject not in hw_grouped:
                hw_grouped[subject] = {
                    "subject": subject,
                    "items": [],
                }
            hw_grouped[subject]["items"].append({
                "id": proof.id,
                "image": proof.image.url if proof.image else None,
                "caption": proof.caption,
                "assignment_title": proof.submission.assignment.title,
                "submitted_at": proof.submission.created_at.isoformat(),
                "user_id": proof.submission.user_id,
            })

        # Creations (2026-04-22 — new "I made a thing" entry type).
        from apps.creations.models import Creation

        creation_qs = filter_queryset_by_role(
            user,
            Creation.objects.select_related(
                "primary_skill", "primary_skill__category", "secondary_skill",
            ),
            role_filter_field="user",
        ).order_by("-created_at")

        creations = [
            {
                "id": c.id,
                "image": c.image.url if c.image else None,
                "audio": c.audio.url if c.audio else None,
                "caption": c.caption,
                "primary_skill_name": c.primary_skill.name if c.primary_skill_id else None,
                "primary_skill_category": (
                    c.primary_skill.category.name if c.primary_skill_id else None
                ),
                "secondary_skill_name": (
                    c.secondary_skill.name if c.secondary_skill_id else None
                ),
                "status": c.status,
                "xp_awarded": c.xp_awarded,
                "bonus_xp_awarded": c.bonus_xp_awarded,
                "created_at": c.created_at.isoformat(),
                "user_id": c.user_id,
            }
            for c in creation_qs
        ]

        return Response({
            "projects": list(grouped.values()),
            "homework": list(hw_grouped.values()),
            "creations": creations,
        })


class ExportPortfolioView(APIView):
    def get(self, request):
        import zipfile
        from django.http import HttpResponse

        photos = filter_queryset_by_role(
            request.user,
            ProjectPhoto.objects.select_related("project"),
            role_filter_field="project__assigned_to",
        )

        if not photos.exists():
            return Response({"error": "No photos to export"}, status=404)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for photo in photos:
                if photo.image:
                    folder = photo.project.title.replace("/", "_")
                    filename = f"{folder}/{photo.id}_{photo.caption or 'photo'}.jpg"
                    try:
                        zf.writestr(filename, photo.image.read())
                    except Exception:
                        logger.warning("Failed to add photo %s to portfolio export", photo.id, exc_info=True)
                        continue

            # Add homework proofs.
            from apps.homework.models import HomeworkProof, HomeworkSubmission

            hw_proofs = filter_queryset_by_role(
                request.user,
                HomeworkProof.objects.filter(
                    submission__status=HomeworkSubmission.Status.APPROVED,
                ).select_related("submission__assignment"),
                role_filter_field="submission__user",
            )

            for proof in hw_proofs:
                if proof.image:
                    subject = proof.submission.assignment.get_subject_display()
                    folder = f"homework/{subject}".replace("/", "_")
                    filename = f"{folder}/{proof.id}_{proof.caption or 'proof'}.jpg"
                    try:
                        zf.writestr(filename, proof.image.read())
                    except Exception:
                        logger.warning("Failed to add homework proof %s to export", proof.id, exc_info=True)

            # Add creations — grouped by primary skill category.
            from apps.creations.models import Creation

            creations = filter_queryset_by_role(
                request.user,
                Creation.objects.select_related(
                    "primary_skill", "primary_skill__category",
                ),
                role_filter_field="user",
            )
            for creation in creations:
                if creation.image:
                    cat = (
                        creation.primary_skill.category.name
                        if creation.primary_skill_id else "misc"
                    )
                    folder = f"creations/{cat}".replace("/", "_")
                    label = (creation.caption or "creation")[:60]
                    filename = f"{folder}/{creation.id}_{label}.jpg"
                    try:
                        zf.writestr(filename, creation.image.read())
                    except Exception:
                        logger.warning(
                            "Failed to add creation %s to export",
                            creation.id, exc_info=True,
                        )

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="portfolio.zip"'
        return response
