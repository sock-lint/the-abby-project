from rest_framework import serializers

from apps.rpg.models import CharacterProfile, Habit, HabitLog


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = CharacterProfile
        fields = [
            "id",
            "username",
            "display_name",
            "level",
            "login_streak",
            "longest_login_streak",
            "last_active_date",
            "perfect_days_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_display_name(self, obj):
        return obj.user.display_name or obj.user.username


class HabitSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()

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
            "coin_reward",
            "xp_reward",
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
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.display_name or obj.created_by.username

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


class HabitWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = [
            "name",
            "icon",
            "habit_type",
            "user",
            "coin_reward",
            "xp_reward",
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
