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
