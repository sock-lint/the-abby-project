from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.achievements.models import Skill
from apps.movement.models import MovementType
from .goals import FACT_TRIGGERS, family_zone


class SkillTagInput(serializers.Serializer):
    skill_id = serializers.IntegerField(min_value=1)
    xp_weight = serializers.IntegerField(min_value=1, max_value=5, default=1)


class GoalWriteSerializer(serializers.Serializer):
    request_id = serializers.UUIDField(required=False)
    user_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    trigger_type = serializers.ChoiceField(choices=sorted(FACT_TRIGGERS - {"badge_earned", "perfect_day", "expedition_returned"}))
    movement_type_id = serializers.IntegerField(required=False, min_value=1)
    metric = serializers.ChoiceField(choices=["count", "minutes", "distance"])
    target = serializers.DecimalField(max_digits=16, decimal_places=3, min_value=Decimal("0.001"))
    unit = serializers.ChoiceField(choices=["actions", "minutes", "mi", "km"])
    period = serializers.ChoiceField(choices=["this_week", "from_today", "custom"], default="this_week")
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    repeat_weekly = serializers.BooleanField(default=False)
    coin_reward = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    xp_reward = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    skill_tags = SkillTagInput(many=True, required=False, default=list)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields) if isinstance(data, dict) else set()
        if unknown:
            raise serializers.ValidationError({field: "Unknown goal field." for field in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, data):
        metric, trigger = data["metric"], data["trigger_type"]
        units = {"count": {"actions"}, "minutes": {"minutes"}, "distance": {"mi", "km"}}
        if data["unit"] not in units[metric]:
            raise serializers.ValidationError({"unit": "Choose a unit that matches the metric."})
        if metric == "count" and data["target"] != data["target"].to_integral_value():
            raise serializers.ValidationError({"target": "Action counts must be whole numbers."})
        if metric == "minutes" and trigger not in {"clock_out", "movement_session"}:
            raise serializers.ValidationError({"metric": "Minutes require tracked work or movement."})
        if metric == "distance" and trigger != "movement_session":
            raise serializers.ValidationError({"metric": "Distance requires movement."})
        if data.get("movement_type_id"):
            if trigger != "movement_session":
                raise serializers.ValidationError({"movement_type_id": "Activity type requires movement."})
        if data["repeat_weekly"] and data["period"] != "this_week":
            raise serializers.ValidationError({"repeat_weekly": "Weekly repeats require a calendar-week goal."})
        if data["period"] == "custom":
            if "start_date" not in data or "end_date" not in data:
                raise serializers.ValidationError({"period": "Custom goals require both dates."})
            start, end = data["start_date"], data["end_date"]
            if end < start or (end - start).days > 365:
                raise serializers.ValidationError({"end_date": "Use an end date on or after today/start, within one year."})
        elif "start_date" in data or "end_date" in data:
            raise serializers.ValidationError({"period": "Dates are only accepted for custom goals."})
        tags = data["skill_tags"]
        ids = [tag["skill_id"] for tag in tags]
        if len(ids) != len(set(ids)) or len(ids) > 3:
            raise serializers.ValidationError({"skill_tags": "Choose up to three different skills."})
        if data["xp_reward"] and not tags:
            raise serializers.ValidationError({"skill_tags": "Choose a skill to receive the XP reward."})
        if not self.context.get("defer_current_eligibility", False):
            self.validate_current_eligibility(data)
        return data

    def validate_current_eligibility(self, data):
        """Check new promises after exact saved-request recovery has been tried."""
        if data.get("movement_type_id"):
            if not MovementType.objects.filter(pk=data["movement_type_id"], is_active=True).exists():
                raise serializers.ValidationError({"movement_type_id": ["Choose an available activity type."]})
        if data["period"] == "custom":
            today = timezone.localtime(timezone.now(), family_zone(self.context["request"].user)).date()
            end = data["end_date"]
            if end < today or (end - today).days > 365:
                raise serializers.ValidationError({"end_date": ["Use an end date on or after today/start, within one year."]})
        ids = {tag["skill_id"] for tag in data.get("skill_tags", [])}
        if Skill.objects.filter(pk__in=ids).count() != len(ids):
            raise serializers.ValidationError({"skill_tags": ["Choose existing skills."]})
        return data


class FutureGoalSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    target = serializers.DecimalField(max_digits=16, decimal_places=3, min_value=Decimal("0.001"), required=False)
    coin_reward = serializers.IntegerField(min_value=0, max_value=10000, required=False)
    xp_reward = serializers.IntegerField(min_value=0, max_value=10000, required=False)
    skill_tags = SkillTagInput(many=True, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Supply only supported future goal fields.")
        return super().to_internal_value(data)


class GoalScheduleSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)
    paused = serializers.BooleanField(required=False)
    next_week = FutureGoalSerializer(required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Supply only supported schedule fields.")
        return super().to_internal_value(data)

    def validate(self, data):
        if "paused" not in data and not data.get("next_week"):
            raise serializers.ValidationError("Choose a pause/resume or future setup change.")
        return data
