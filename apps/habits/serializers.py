from django.utils import timezone
from rest_framework import serializers

from apps.habits.models import Habit, HabitLog


class HabitSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.display_label", read_only=True,
    )
    color = serializers.SerializerMethodField()
    taps_today = serializers.SerializerMethodField()

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "strength",
            "color",
            "taps_today",
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
