from rest_framework import serializers

from .models import ProjectPhoto


class ProjectPhotoSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = ProjectPhoto
        fields = [
            "id", "project", "project_title", "user", "image",
            "video_url", "caption", "is_timelapse", "uploaded_at",
        ]
        read_only_fields = ["user", "uploaded_at"]
