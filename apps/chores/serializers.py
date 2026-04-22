from rest_framework import serializers

from .models import Chore, ChoreCompletion, ChoreSkillTag


class ChoreSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = ChoreSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]
        read_only_fields = ["id", "skill_name", "skill_category"]


class ChoreSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(
        source="assigned_to.display_label", read_only=True, allow_null=True,
    )
    is_available = serializers.BooleanField(read_only=True, default=False)
    today_status = serializers.CharField(read_only=True, default=None)
    today_completion_id = serializers.IntegerField(read_only=True, default=None)
    skill_tags = ChoreSkillTagSerializer(many=True, read_only=True)

    class Meta:
        model = Chore
        fields = [
            "id", "title", "description", "icon",
            "reward_amount", "coin_reward", "xp_reward",
            "recurrence", "week_schedule", "schedule_start_date",
            "assigned_to", "assigned_to_name",
            "is_active", "order",
            "is_available", "today_status", "today_completion_id",
            "skill_tags",
            "created_at", "updated_at",
        ]


class ChoreWriteSerializer(serializers.ModelSerializer):
    # Accept skill_tags in the same request body as chore create/update —
    # list of {skill_id, xp_weight} dicts. Handled by the viewset's
    # perform_create / perform_update hooks.
    #
    # No ``default=list`` on purpose: we need to distinguish "field not
    # provided" (leave tags alone on update) from "empty list provided"
    # (strip all tags). ``required=False`` without default means missing
    # key → not in validated_data, empty list → in validated_data as [].
    #
    # ``write_only=True`` is load-bearing: DRF's ``create()`` re-serializes
    # the saved instance with the same serializer for its Response body,
    # and without ``write_only`` DRF would try to coerce the reverse-FK
    # RelatedManager (``chore.skill_tags``) through ListField.to_representation
    # and crash with "'RelatedManager' object is not iterable". The read
    # surface comes from ``ChoreSerializer.skill_tags`` (nested, tag-aware).
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True,
    )

    class Meta:
        model = Chore
        fields = [
            "title", "description", "icon",
            "reward_amount", "coin_reward", "xp_reward",
            "recurrence", "week_schedule", "schedule_start_date",
            "assigned_to", "is_active", "order",
            "skill_tags",
        ]


class ChoreCompletionSerializer(serializers.ModelSerializer):
    chore_title = serializers.CharField(source="chore.title", read_only=True)
    chore_icon = serializers.CharField(source="chore.icon", read_only=True)
    user_name = serializers.CharField(source="user.display_label", read_only=True)

    class Meta:
        model = ChoreCompletion
        fields = [
            "id", "chore", "chore_title", "chore_icon",
            "user", "user_name",
            "completed_date", "status", "notes",
            "decided_at", "decided_by",
            "reward_amount_snapshot", "coin_reward_snapshot",
            "created_at",
        ]
        read_only_fields = fields
