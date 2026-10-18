from rest_framework import serializers

from apps.chronicle.models import ChronicleComment, ChronicleEntry
from apps.notifications.services import get_display_name


class ChronicleEntrySerializer(serializers.ModelSerializer):
    reward_receipt = serializers.SerializerMethodField()

    def get_reward_receipt(self, entry):
        if entry.kind not in (ChronicleEntry.Kind.JOURNAL, ChronicleEntry.Kind.DAILY_NOTE, ChronicleEntry.Kind.GRADE):
            return None
        receipt = entry.metadata.get("reward_receipt", {
            "status": "unavailable", "xp_awarded": 0, "skills": [],
        })
        if entry.kind in (ChronicleEntry.Kind.JOURNAL, ChronicleEntry.Kind.DAILY_NOTE):
            # Old rows have no verified coin receipt; never infer a payout.
            return {"coins_awarded": 0, "coin_status": "unavailable", **receipt}
        return receipt

    class Meta:
        model = ChronicleEntry
        fields = (
            "id", "kind", "occurred_on", "chapter_year", "title", "summary",
            "icon_slug", "event_slug", "related_object_type", "related_object_id",
            "metadata", "viewed_at", "created_at", "is_private", "user",
            "client_entry_id", "reward_receipt",
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
    is_private = serializers.BooleanField(required=False, default=True)
    client_entry_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if not self.partial and not (data.get("title", "").strip() or data.get("summary", "").strip()):
            raise serializers.ValidationError("Write a title or a few words before saving your memory.")
        return data


class ChronicleCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source="author.role", read_only=True)

    def get_author_name(self, comment):
        return get_display_name(comment.author)

    class Meta:
        model = ChronicleComment
        fields = (
            "id", "entry", "author", "author_name", "author_role", "body",
            "created_at", "client_comment_id",
        )
        read_only_fields = fields


class ChronicleCommentWriteSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000, allow_blank=False)
    client_comment_id = serializers.UUIDField(required=False)


class ManualEntryCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ChronicleEntry
        fields = ("user_id", "title", "summary", "icon_slug", "occurred_on", "metadata")


class ManualEntryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChronicleEntry
        fields = ("title", "summary", "icon_slug", "occurred_on", "metadata")
