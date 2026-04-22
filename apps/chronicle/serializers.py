from rest_framework import serializers

from apps.chronicle.models import ChronicleEntry


class ChronicleEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChronicleEntry
        fields = (
            "id", "kind", "occurred_on", "chapter_year", "title", "summary",
            "icon_slug", "event_slug", "related_object_type", "related_object_id",
            "metadata", "viewed_at", "created_at",
        )
        read_only_fields = fields


class ManualEntryCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ChronicleEntry
        fields = ("user_id", "title", "summary", "icon_slug", "occurred_on", "metadata")
