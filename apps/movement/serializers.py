from decimal import Decimal

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
            "created_by",
        ]
        read_only_fields = fields


class MovementTypeWriteSerializer(serializers.Serializer):
    """Write payload for POST /api/movement-types/.

    Routes into ``MovementTypeService.create_type``.
    """

    name = serializers.CharField(required=True, max_length=64, allow_blank=False)
    icon = serializers.CharField(required=False, allow_blank=True, max_length=10)
    default_intensity = serializers.ChoiceField(
        choices=MovementType.Intensity.choices,
        required=False,
        default=MovementType.Intensity.MEDIUM,
    )
    primary_skill_id = serializers.IntegerField(required=True)
    secondary_skill_id = serializers.IntegerField(
        required=False, allow_null=True,
    )


class MovementSessionSerializer(serializers.ModelSerializer):
    distance = serializers.SerializerMethodField()
    challenge_receipts = serializers.SerializerMethodField()

    def get_distance(self, obj):
        if obj.distance_meters is None:
            return None
        divisor = Decimal("1609.344") if obj.distance_unit == "mi" else Decimal("1000")
        return format((obj.distance_meters / divisor).normalize(), "f")

    def get_challenge_receipts(self, obj):
        return getattr(obj, "_challenge_receipts", [])
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
            "distance_meters", "distance", "distance_unit", "client_request_id", "challenge_receipts",
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
    distance = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal("0.001"), max_value=Decimal("1000"), required=False)
    distance_unit = serializers.ChoiceField(choices=["mi", "km"], default="mi")
    client_request_id = serializers.UUIDField(required=False)
