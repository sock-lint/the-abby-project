"""Bounded, explicit input/output shapes for reviewed project plans."""
from decimal import Decimal

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unsupported fields in project plan."]})
        return super().to_internal_value(data)


class ProjectPlanRequestSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=10000, allow_blank=True, required=False, default="")
    difficulty = serializers.IntegerField(min_value=1, max_value=5, required=False, default=2)
    guidance = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")


class ExistingProjectPlanRequestSerializer(StrictSerializer):
    guidance = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")


class MilestonePlanSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")


class MilestoneIndexField(serializers.Field):
    def to_internal_value(self, data):
        if type(data) is not int:
            raise serializers.ValidationError("Use an integer milestone index or null.")
        return data

    def to_representation(self, value):
        return value


class StepPlanSerializer(MilestonePlanSerializer):
    milestone_index = MilestoneIndexField(allow_null=True, required=False, default=None)


class MaterialPlanSerializer(StrictSerializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")
    estimated_cost = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.00"), required=False, default=Decimal("0.00"),
    )


class ProjectPlanSerializer(StrictSerializer):
    milestones = MilestonePlanSerializer(many=True, max_length=10, required=False, default=list)
    steps = StepPlanSerializer(many=True, min_length=1, max_length=40)
    materials = MaterialPlanSerializer(many=True, max_length=40, required=False, default=list)

    def validate(self, attrs):
        count = len(attrs["milestones"])
        for step in attrs["steps"]:
            index = step["milestone_index"]
            if index is not None and not 0 <= index < count:
                raise serializers.ValidationError({"steps": "A milestone index must refer to this plan's milestones."})
        return attrs


class ApplyProjectPlanSerializer(StrictSerializer):
    plan = ProjectPlanSerializer()
    plan_version = serializers.RegexField(r"^[a-f0-9]{64}$", max_length=64)
