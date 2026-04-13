import io
import logging

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import RoleFilteredQuerySetMixin

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


class PortfolioView(APIView):
    def get(self, request):
        user = request.user

        # Project photos (existing).
        photos = ProjectPhoto.objects.select_related("project")
        if user.role != "parent":
            photos = photos.filter(project__assigned_to=user)

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

        hw_proofs = HomeworkProof.objects.filter(
            submission__status=HomeworkSubmission.Status.APPROVED,
        ).select_related("submission__assignment")
        if user.role != "parent":
            hw_proofs = hw_proofs.filter(submission__user=user)

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
            })

        return Response({
            "projects": list(grouped.values()),
            "homework": list(hw_grouped.values()),
        })


class ExportPortfolioView(APIView):
    def get(self, request):
        import zipfile
        from django.http import HttpResponse

        photos = ProjectPhoto.objects.select_related("project")
        if request.user.role == "child":
            photos = photos.filter(project__assigned_to=request.user)

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

            hw_proofs = HomeworkProof.objects.filter(
                submission__status=HomeworkSubmission.Status.APPROVED,
            ).select_related("submission__assignment")
            if request.user.role == "child":
                hw_proofs = hw_proofs.filter(submission__user=request.user)

            for proof in hw_proofs:
                if proof.image:
                    subject = proof.submission.assignment.get_subject_display()
                    folder = f"homework/{subject}".replace("/", "_")
                    filename = f"{folder}/{proof.id}_{proof.caption or 'proof'}.jpg"
                    try:
                        zf.writestr(filename, proof.image.read())
                    except Exception:
                        logger.warning("Failed to add homework proof %s to export", proof.id, exc_info=True)

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="portfolio.zip"'
        return response
