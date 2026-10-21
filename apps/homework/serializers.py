import re

from django.db import transaction
from rest_framework import serializers

from .models import (
    HomeworkAssignment,
    HomeworkProof,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)


class HomeworkAISettingsWriteSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(
        choices=["default", "openai", "anthropic"],
        error_messages={"invalid_choice": "Select a supported AI provider."},
    )
    model = serializers.CharField(max_length=128, allow_blank=True, trim_whitespace=False)
    api_key = serializers.CharField(
        required=False, allow_blank=True, max_length=4096, trim_whitespace=False,
        write_only=True,
    )

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({
                "non_field_errors": ["Only provider, model and API key may be supplied."],
            })
        return super().to_internal_value(data)

    def validate_api_key(self, value):
        if any(not 33 <= ord(char) <= 126 for char in value):
            raise serializers.ValidationError("Enter an API key using printable characters without spaces.")
        return value

    def validate(self, attrs):
        if attrs["provider"] != "default" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", attrs["model"]):
            raise serializers.ValidationError({"model": "Enter a valid model ID."})
        return attrs


class HomeworkSkillTagSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)

    class Meta:
        model = HomeworkSkillTag
        fields = ["id", "skill", "skill_name", "xp_amount"]
        read_only_fields = ["id", "skill_name"]


class HomeworkProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeworkProof
        fields = ["id", "image", "caption", "order"]
        read_only_fields = ["id"]


class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    proofs = HomeworkProofSerializer(many=True, read_only=True)
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    assignment_subject = serializers.CharField(source="assignment.subject", read_only=True)
    assignment_created_by_role = serializers.CharField(
        source="assignment.created_by.role", read_only=True,
    )
    user_name = serializers.CharField(source="user.display_label", read_only=True)
    current_due_date = serializers.DateField(source="assignment.due_date", read_only=True)

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id", "assignment", "assignment_title", "assignment_subject",
            "assignment_created_by_role",
            "user", "user_name",
            "status", "notes", "proof_url",
            "decided_at", "decided_by",
            "timeliness", "timing_snapshot", "current_due_date",
            "proofs",
            "created_at",
        ]
        read_only_fields = fields


class HomeworkSubmissionStatusSerializer(serializers.ModelSerializer):
    """Only the matching child's saved timing belongs on an assignment card."""

    class Meta:
        model = HomeworkSubmission
        fields = ["id", "status", "timeliness", "timing_snapshot", "created_at", "decided_at"]
        read_only_fields = fields


class HomeworkAssignmentSerializer(serializers.ModelSerializer):
    skill_tags = HomeworkSkillTagSerializer(many=True, read_only=True)
    assigned_to_name = serializers.CharField(
        source="assigned_to.display_label", read_only=True,
    )
    created_by_name = serializers.CharField(
        source="created_by.display_label", read_only=True,
    )
    submission_status = serializers.SerializerMethodField()
    timeliness_preview = serializers.SerializerMethodField()
    has_project = serializers.SerializerMethodField()
    can_plan = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "subject",
            "effort_level", "due_date",
            "assigned_to", "assigned_to_name",
            "created_by", "created_by_name",
            "is_active", "notes",
            "project", "has_project", "can_plan",
            "skill_tags",
            "submission_status", "timeliness_preview",
            "created_at", "updated_at",
        ]

    def get_submission_status(self, obj):
        # Iterate the prefetched manager rather than re-querying with
        # .exclude(...).first() — that call bypasses the prefetch cache
        # and fires one query per assignment in list views.
        for sub in obj.submissions.all():
            if sub.user_id == obj.assigned_to_id and sub.status != HomeworkSubmission.Status.REJECTED:
                return {
                    **HomeworkSubmissionStatusSerializer(sub).data,
                    "current_due_date": obj.due_date.isoformat(),
                }
        return None

    def get_timeliness_preview(self, obj):
        from .services import HomeworkService
        from config.submission_timing import submission_context

        request = self.context.get("request")
        user = request.user if request else obj.assigned_to
        return {"timeliness": HomeworkService.get_timeliness(obj.due_date, submit_date=submission_context(user)[2])}

    def get_has_project(self, obj):
        return obj.project_id is not None

    def get_can_plan(self, obj):
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        from .services import HomeworkService

        return HomeworkService.can_self_plan(request.user, obj)


class HomeworkAssignmentWriteSerializer(serializers.ModelSerializer):
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False, default=list, write_only=True,
    )

    class Meta:
        model = HomeworkAssignment
        fields = [
            "title", "description", "subject",
            "effort_level", "due_date",
            "assigned_to",
            "notes", "skill_tags",
        ]
        # ``assigned_to`` is optional on write — children omit it entirely
        # (the viewset's ``perform_create`` auto-sets it to the request
        # user) and parents supply it explicitly.
        extra_kwargs = {
            "assigned_to": {"required": False},
        }

    def validate_effort_level(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Effort level must be between 1 and 5.")
        return value


class HomeworkTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeworkTemplate
        fields = [
            "id", "title", "description", "subject",
            "effort_level",
            "skill_tags", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _admit_tags(self, data, *, instance=None):
        from apps.achievements.models import Skill
        from apps.rpg.taxonomy_references import admit_references
        tags = data.get("skill_tags", [])
        if not isinstance(tags, list) or any(not isinstance(row, dict) or type(row.get("skill_id")) is not int for row in tags):
            raise serializers.ValidationError({"skill_tags": "Choose existing skills."})
        admit_references(Skill, [row["skill_id"] for row in tags],
                         retained_ids=[row.get("skill_id") for row in instance.skill_tags] if instance else (),
                         error_type=serializers.ValidationError)

    @transaction.atomic
    def create(self, validated_data):
        self._admit_tags(validated_data)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        from django.shortcuts import get_object_or_404
        owner = getattr(self.context.get("request"), "user", None)
        current = HomeworkTemplate.objects.select_for_update(of=("self",)).filter(pk=instance.pk, created_by_id=instance.created_by_id)
        if owner is not None:
            current = current.filter(created_by_id=owner.pk, created_by__family_id=owner.family_id)
        instance = get_object_or_404(current)
        self._admit_tags(validated_data, instance=instance)
        return super().update(instance, validated_data)
