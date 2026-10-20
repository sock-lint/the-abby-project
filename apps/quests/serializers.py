from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from apps.rpg.catalog_icons import challenge_catalog_icon, item_catalog_icon

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
    item_catalog_icon = serializers.SerializerMethodField()
    item_name = serializers.CharField(source="item.display_name", read_only=True)
    item_icon = serializers.CharField(source="item.icon", read_only=True)
    item_sprite_key = serializers.CharField(source="item.sprite_key", read_only=True)

    class Meta:
        model = QuestRewardItem
        fields = ["id", "item", "item_name", "item_icon", "item_sprite_key", "item_catalog_icon", "quantity"]
        read_only_fields = fields

    def get_item_catalog_icon(self, obj):
        cache = self.context.get("reward_item_details_cache")
        if cache is not None:
            from .reward_items import reward_item_details

            return reward_item_details(obj.item, cache=cache)["item_catalog_icon"]
        return item_catalog_icon(obj.item)

    def to_representation(self, instance):
        from .reward_items import reward_item_details

        data = super().to_representation(instance)
        data.update(reward_item_details(
            instance.item, snapshot=getattr(instance, "reward_snapshot", None),
            cache=self.context.get("reward_item_details_cache"),
        ))
        return data


class QuestSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = QuestSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]
        read_only_fields = ["id", "skill_name", "skill_category"]


class QuestDefinitionSerializer(serializers.ModelSerializer):
    catalog_icon = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    reward_items = serializers.SerializerMethodField()
    skill_tags = QuestSkillTagSerializer(many=True, read_only=True)
    quest_type_display = serializers.CharField(source="get_quest_type_display", read_only=True)
    # Frontend uses this to classify gated quests into the "Locked" codex
    # chapter — compared against the user's earned badge ids client-side.
    required_badge = serializers.PrimaryKeyRelatedField(read_only=True)
    required_badge_name = serializers.CharField(
        source="required_badge.name", read_only=True, default=None,
    )
    prerequisite_quest = serializers.PrimaryKeyRelatedField(read_only=True)
    prerequisite_quest_name = serializers.CharField(source="prerequisite_quest.name", read_only=True, default=None)
    required_skill = serializers.PrimaryKeyRelatedField(read_only=True)
    required_skill_name = serializers.CharField(source="required_skill.name", read_only=True, default=None)
    milestone_eligibility = serializers.SerializerMethodField()

    def get_milestone_eligibility(self, obj):
        from .milestone_eligibility import milestone_eligibility
        user = self.context.get("eligibility_user") or getattr(self.context.get("request"), "user", None)
        return milestone_eligibility(user, obj)

    def get_reward_items(self, obj):
        from apps.rpg.catalog_support import item_is_available
        rewards = [reward for reward in obj.reward_items.all() if item_is_available(reward.item)]
        return QuestRewardItemSerializer(rewards, many=True, context=self.context).data

    def get_catalog_available(self, obj):
        if obj.required_badge_id is None:
            return True
        from apps.achievements.availability import badge_goal_is_available
        from apps.achievements.models import UserBadge
        request = self.context.get("request")
        user = self.context.get("eligibility_user") or getattr(request, "user", None)
        if user and UserBadge.objects.filter(user=user, badge_id=obj.required_badge_id).exists():
            return True
        return badge_goal_is_available(obj.required_badge, user)

    def get_catalog_icon(self, obj):
        return challenge_catalog_icon(obj)

    class Meta:
        model = QuestDefinition
        fields = [
            "id", "name", "description", "icon", "sprite_key", "catalog_icon", "quest_type", "quest_type_display",
            "target_value", "duration_days", "trigger_filter",
            "coin_reward", "xp_reward", "reward_items", "skill_tags",
            "required_badge", "required_badge_name",
            "prerequisite_quest", "prerequisite_quest_name", "required_skill", "required_skill_name",
            "required_skill_level", "milestone_eligibility",
            "is_repeatable", "is_system", "created_at", "catalog_available",
        ]
        read_only_fields = fields


class QuestParticipantSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_label", read_only=True)

    class Meta:
        model = QuestParticipant
        fields = ["id", "user", "user_name", "contribution"]
        read_only_fields = fields


class QuestSerializer(serializers.ModelSerializer):
    definition = serializers.SerializerMethodField()

    def get_definition(self, obj):
        from .reward_items import accepted_reward_items

        data = QuestDefinitionSerializer(obj.definition, context=self.context).data
        data["reward_items"] = QuestRewardItemSerializer(
            accepted_reward_items(obj), many=True, context=self.context,
        ).data
        return data
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
