from rest_framework import serializers

from apps.movement.models import (
    MovementSession,
    MovementType,
    MovementTypeSkillTag,
)


class MovementTypeSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = MovementTypeSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]


class MovementTypeSerializer(serializers.ModelSerializer):
    skill_tags = MovementTypeSkillTagSerializer(many=True, read_only=True)

    class Meta:
        model = MovementType
        fields = [
            "id", "name", "slug", "icon",
            "default_intensity", "is_active", "order", "skill_tags",
        ]
        read_only_fields = fields


class MovementSessionSerializer(serializers.ModelSerializer):
    movement_type_name = serializers.CharField(
        source="movement_type.name", read_only=True,
    )
    movement_type_icon = serializers.CharField(
        source="movement_type.icon", read_only=True,
    )
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = MovementSession
        fields = [
            "id", "user", "user_display",
            "movement_type", "movement_type_name", "movement_type_icon",
            "duration_minutes", "intensity",
            "occurred_on", "notes", "xp_awarded", "created_at",
        ]
        read_only_fields = fields

    def get_user_display(self, obj):
        u = obj.user
        return (
            u.get_full_name()
            or getattr(u, "display_name", "")
            or u.username
        )


class MovementSessionWriteSerializer(serializers.Serializer):
    """Write payload for POST /api/movement-sessions/.

    The viewset routes these into ``MovementSessionService.log_session``.
    """

    movement_type_id = serializers.IntegerField(required=True)
    duration_minutes = serializers.IntegerField(
        required=True,
        min_value=1,
        max_value=600,
    )
    intensity = serializers.ChoiceField(
        choices=MovementSession.Intensity.choices,
        required=False,
        default=MovementSession.Intensity.MEDIUM,
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=200)
