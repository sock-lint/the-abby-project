from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    DailyChallenge,
    Quest,
    QuestDefinition,
    QuestParticipant,
    QuestRewardItem,
    QuestSkillTag,
)
from .validators import validate_trigger_filter


class DailyChallengeSerializer(serializers.ModelSerializer):
    challenge_type_display = serializers.CharField(
        source="get_challenge_type_display", read_only=True,
    )
    is_complete = serializers.BooleanField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = DailyChallenge
        fields = [
            "id", "challenge_type", "challenge_type_display",
            "target_value", "current_progress", "progress_percent",
            "date", "completed_at", "coin_reward", "xp_reward",
            "is_complete",
        ]
        read_only_fields = fields


class QuestRewardItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_icon = serializers.CharField(source="item.icon", read_only=True)
    item_sprite_key = serializers.CharField(source="item.sprite_key", read_only=True)

    class Meta:
        model = QuestRewardItem
        fields = ["id", "item", "item_name", "item_icon", "item_sprite_key", "quantity"]
        read_only_fields = fields


class QuestSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = QuestSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]
        read_only_fields = ["id", "skill_name", "skill_category"]


class QuestDefinitionSerializer(serializers.ModelSerializer):
    reward_items = QuestRewardItemSerializer(many=True, read_only=True)
    skill_tags = QuestSkillTagSerializer(many=True, read_only=True)
    quest_type_display = serializers.CharField(source="get_quest_type_display", read_only=True)

    class Meta:
        model = QuestDefinition
        fields = [
            "id", "name", "description", "icon", "sprite_key", "quest_type", "quest_type_display",
            "target_value", "duration_days", "trigger_filter",
            "coin_reward", "xp_reward", "reward_items", "skill_tags",
            "is_repeatable", "is_system", "created_at",
        ]
        read_only_fields = fields


class QuestParticipantSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_label", read_only=True)

    class Meta:
        model = QuestParticipant
        fields = ["id", "user", "user_name", "contribution"]
        read_only_fields = fields


class QuestSerializer(serializers.ModelSerializer):
    definition = QuestDefinitionSerializer(read_only=True)
    participants = QuestParticipantSerializer(many=True, read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    effective_target = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quest
        fields = [
            "id", "definition", "status", "start_date", "end_date",
            "current_progress", "rage_shield", "effective_target",
            "progress_percent", "participants", "created_at",
        ]
        read_only_fields = fields


class QuestWriteSerializer(serializers.Serializer):
    """For parent-created quests."""
    name = serializers.CharField(max_length=100)
    description = serializers.CharField()
    icon = serializers.CharField(max_length=50, default="\u2694\ufe0f")
    quest_type = serializers.ChoiceField(choices=["boss", "collection"])
    target_value = serializers.IntegerField(min_value=1)
    duration_days = serializers.IntegerField(min_value=1, default=7)
    coin_reward = serializers.IntegerField(min_value=0, default=0)
    xp_reward = serializers.IntegerField(min_value=0, default=0)
    trigger_filter = serializers.JSONField(required=False, default=dict)
    assigned_to = serializers.IntegerField(required=False)  # child user ID
    # Co-op: when 2+ ids are passed, the quest is started as a shared
    # ``Quest`` with a ``QuestParticipant`` per child. ``assigned_to`` is
    # ignored when ``coop_user_ids`` is set.
    coop_user_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True,
    )
    # Optional XP fanout \u2014 list of {skill_id, xp_weight} dicts. Mirrors
    # the chore/habit shape so authors can set both at create time.
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True,
        write_only=True,
    )

    def validate_trigger_filter(self, value):
        try:
            validate_trigger_filter(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value

    def validate_coop_user_ids(self, value):
        if value is None:
            return value
        if value and len(value) < 2:
            raise serializers.ValidationError(
                "coop_user_ids must contain at least 2 children"
            )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("coop_user_ids contains duplicates")
        return value

    def validate_skill_tags(self, value):
        # Light pre-validation; FK existence is checked at apply time so
        # invalid skill_ids surface as a 400 with the offending row, not
        # a 500 from IntegrityError.
        if not value:
            return value
        for row in value:
            if "skill_id" not in row:
                raise serializers.ValidationError(
                    "skill_tags rows must include skill_id"
                )
            weight = row.get("xp_weight", 1)
            if not isinstance(weight, int) or weight < 1 or weight > 5:
                raise serializers.ValidationError(
                    "skill_tags xp_weight must be an integer 1-5"
                )
        return value
