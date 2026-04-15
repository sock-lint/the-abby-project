from rest_framework import serializers

from .models import ProjectIngestionJob


class ProjectIngestionJobSerializer(serializers.ModelSerializer):
    """Read/write serializer for the ingest staging job.

    ``result_json`` is writable so the parent can edit the staged draft
    from the preview screen before committing.
    """

    class Meta:
        model = ProjectIngestionJob
        fields = [
            "id", "source_type", "source_url", "source_file", "status",
            "result_json", "error", "project", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "error", "project", "created_at", "updated_at",
        ]
