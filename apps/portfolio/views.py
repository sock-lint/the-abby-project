import io

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProjectPhoto
from .serializers import ProjectPhotoSerializer


class ProjectPhotoViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectPhotoSerializer

    def get_queryset(self):
        user = self.request.user
        qs = ProjectPhoto.objects.select_related("project")
        if user.role == "child":
            qs = qs.filter(project__assigned_to=user)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PortfolioView(APIView):
    def get(self, request):
        user = request.user
        photos = ProjectPhoto.objects.select_related("project")
        if user.role == "child":
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

        return Response(list(grouped.values()))


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
                        continue

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="portfolio.zip"'
        return response
