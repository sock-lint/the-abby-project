from rest_framework import serializers

from .models import ActivityEvent


class _UserBriefField(serializers.Field):
    """Serialize an optional user FK to {id, display_name}."""

    def to_representation(self, user):
        if user is None:
            return None
        return {
            "id": user.pk,
            "display_name": (user.display_name or user.username)
                if hasattr(user, "display_name") else user.username,
            "role": getattr(user, "role", None),
        }


class _TargetField(serializers.Field):
    """Flatten the GenericForeignKey to {ct, id, repr} — safe for nulls."""

    def to_representation(self, obj: ActivityEvent):
        if obj.target_ct_id is None or obj.target_id is None:
            return None
        target = obj.target  # resolved through the GenericForeignKey
        ct = obj.target_ct
        return {
            "ct": f"{ct.app_label}.{ct.model}" if ct else None,
            "id": obj.target_id,
            "repr": str(target) if target is not None else None,
        }


class ActivityEventSerializer(serializers.ModelSerializer):
    actor = _UserBriefField(read_only=True)
    subject = _UserBriefField(read_only=True)
    target = serializers.SerializerMethodField()

    class Meta:
        model = ActivityEvent
        fields = [
            "id",
            "occurred_at",
            "category",
            "event_type",
            "summary",
            "actor",
            "subject",
            "target",
            "coins_delta",
            "money_delta",
            "xp_delta",
            "context",
            "correlation_id",
        ]
        read_only_fields = fields

    def get_target(self, obj):
        return _TargetField().to_representation(obj)
