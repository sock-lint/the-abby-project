from rest_framework import serializers

from .models import Chore, ChoreCompletion


class ChoreSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(read_only=True, default=False)
    today_status = serializers.CharField(read_only=True, default=None)
    today_completion_id = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Chore
        fields = [
            "id", "title", "description", "icon",
            "reward_amount", "coin_reward",
            "recurrence", "week_schedule", "schedule_start_date",
            "assigned_to", "assigned_to_name",
            "is_active", "order",
            "is_available", "today_status", "today_completion_id",
            "created_at", "updated_at",
        ]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.display_name or obj.assigned_to.username
        return None


class ChoreWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chore
        fields = [
            "title", "description", "icon",
            "reward_amount", "coin_reward",
            "recurrence", "week_schedule", "schedule_start_date",
            "assigned_to", "is_active", "order",
        ]


class ChoreCompletionSerializer(serializers.ModelSerializer):
    chore_title = serializers.CharField(source="chore.title", read_only=True)
    chore_icon = serializers.CharField(source="chore.icon", read_only=True)
    user_name = serializers.SerializerMethodField()

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

    def get_user_name(self, obj):
        return obj.user.display_name or obj.user.username
