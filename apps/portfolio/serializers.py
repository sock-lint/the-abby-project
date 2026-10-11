from rest_framework import serializers

from config.viewsets import filter_projects_accessible_to

from .models import ProjectPhoto


class ProjectPhotoSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is not None:
            fields["project"].queryset = filter_projects_accessible_to(
                request.user, fields["project"].queryset,
            )
        return fields

    class Meta:
        model = ProjectPhoto
        fields = [
            "id", "project", "project_title", "user", "image",
            "video_url", "caption", "is_timelapse", "uploaded_at",
        ]
        read_only_fields = ["user", "uploaded_at"]
