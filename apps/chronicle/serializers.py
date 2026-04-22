from rest_framework import serializers

from apps.chronicle.models import ChronicleEntry


class ChronicleEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChronicleEntry
        fields = (
            "id", "kind", "occurred_on", "chapter_year", "title", "summary",
            "icon_slug", "event_slug", "related_object_type", "related_object_id",
            "metadata", "viewed_at", "created_at", "is_private", "user",
        )
        read_only_fields = fields


class JournalEntryWriteSerializer(serializers.Serializer):
    """Input shape for child-authored journal POST/PATCH.

    ``user_id`` is intentionally absent — the viewset binds writes to
    ``request.user`` so a malicious client can't target another child.
    """
    title = serializers.CharField(
        max_length=160, required=False, allow_blank=True,
    )
    summary = serializers.CharField(required=False, allow_blank=True)


class ManualEntryCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ChronicleEntry
        fields = ("user_id", "title", "summary", "icon_slug", "occurred_on", "metadata")


class ManualEntryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChronicleEntry
        fields = ("title", "summary", "icon_slug", "occurred_on", "metadata")
