from rest_framework import serializers

from apps.creations.models import Creation, CreationBonusSkillTag


class CreationBonusSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = CreationBonusSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]


class CreationSerializer(serializers.ModelSerializer):
    """Read serializer — used for GET list/detail, POST response body,
    and Sketchbook/approval-queue aggregation on the frontend.
    """

    image = serializers.ImageField(read_only=True)
    audio = serializers.FileField(read_only=True)
    user_display = serializers.SerializerMethodField()
    primary_skill_name = serializers.CharField(source="primary_skill.name", read_only=True)
    primary_skill_category = serializers.CharField(
        source="primary_skill.category.name", read_only=True
    )
    secondary_skill_name = serializers.CharField(
        source="secondary_skill.name", read_only=True, default=None,
    )
    bonus_skill_tags = CreationBonusSkillTagSerializer(many=True, read_only=True)

    class Meta:
        model = Creation
        fields = [
            "id",
            "user",
            "user_display",
            "image",
            "audio",
            "caption",
            "occurred_on",
            "primary_skill",
            "primary_skill_name",
            "primary_skill_category",
            "secondary_skill",
            "secondary_skill_name",
            "status",
            "xp_awarded",
            "bonus_xp_awarded",
            "bonus_skill_tags",
            "decided_at",
            "decided_by",
            "chronicle_entry",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_display(self, obj):
        u = obj.user
        return (
            u.get_full_name()
            or getattr(u, "display_name", "")
            or u.username
        )


class CreationWriteSerializer(serializers.Serializer):
    """Write serializer for POST /api/creations/.

    Multipart-first — the image field is required, audio is optional.
    Caller passes ``primary_skill_id`` + optional ``secondary_skill_id``
    as form fields; the viewset routes these into ``CreationService.log_creation``.
    """

    image = serializers.ImageField(required=True)
    audio = serializers.FileField(required=False, allow_null=True)
    caption = serializers.CharField(required=False, allow_blank=True, max_length=200)
    primary_skill_id = serializers.IntegerField(required=True)
    secondary_skill_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_audio(self, value):
        if value is None:
            return value
        # 10 MB soft cap — matches the client-side check in CreationLogModal.
        if value.size and value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Audio file must be under 10 MB.")
        return value


class CreationApproveSerializer(serializers.Serializer):
    """Write serializer for POST /api/creations/{id}/approve/."""

    bonus_xp = serializers.IntegerField(required=False, min_value=0, max_value=100)
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
