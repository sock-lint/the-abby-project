from django.utils import timezone
from rest_framework import serializers

from apps.habits.models import Habit, HabitLog, HabitSkillTag


class HabitSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model = HabitSkillTag
        fields = ["id", "skill", "skill_name", "skill_category", "xp_weight"]
        read_only_fields = ["id", "skill_name", "skill_category"]


class HabitSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.display_label", read_only=True,
    )
    color = serializers.SerializerMethodField()
    taps_today = serializers.SerializerMethodField()
    skill_tags = HabitSkillTagSerializer(many=True, read_only=True)

    class Meta:
        model = Habit
        fields = [
            "id",
            "name",
            "icon",
            "habit_type",
            "user",
            "created_by",
            "created_by_name",
            "xp_reward",
            "max_taps_per_day",
            "taps_today",
            "strength",
            "color",
            "is_active",
            "pending_parent_review",
            "skill_tags",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "strength",
            "color",
            "taps_today",
            "pending_parent_review",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_color(self, obj):
        s = obj.strength
        if s < -5:
            return "red-dark"
        if s < 0:
            return "red-light"
        if s == 0:
            return "yellow"
        if s <= 5:
            return "green-light"
        if s <= 10:
            return "green"
        return "blue"

    def get_taps_today(self, obj):
        return HabitLog.objects.filter(
            habit=obj,
            user=obj.user,
            direction=1,
            created_at__date=timezone.localdate(),
        ).count()


class HabitWriteSerializer(serializers.ModelSerializer):
    # Accept skill_tags in the same request body as habit create/update.
    # Replacement semantics: passing a list overwrites the existing tag
    # set; omitting the field leaves tags unchanged (no default=list).
    # ``write_only=True`` — read surface is HabitSerializer.skill_tags
    # (nested). Without it, DRF's ``create()`` response body serialization
    # would run ListField over the reverse-FK manager and crash.
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True,
    )

    class Meta:
        model = Habit
        fields = [
            "name",
            "icon",
            "habit_type",
            "user",
            "xp_reward",
            "max_taps_per_day",
            "is_active",
            "skill_tags",
        ]


class HabitLogSerializer(serializers.ModelSerializer):
    habit_name = serializers.CharField(source="habit.name", read_only=True)
    habit_icon = serializers.CharField(source="habit.icon", read_only=True)

    class Meta:
        model = HabitLog
        fields = [
            "id",
            "habit",
            "habit_name",
            "habit_icon",
            "user",
            "direction",
            "streak_at_time",
            "created_at",
        ]
        read_only_fields = fields
