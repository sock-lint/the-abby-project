from rest_framework import serializers

from .models import (
    HomeworkAssignment,
    HomeworkProof,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)


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

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id", "assignment", "assignment_title", "assignment_subject",
            "assignment_created_by_role",
            "user", "user_name",
            "status", "notes",
            "decided_at", "decided_by",
            "timeliness",
            "proofs",
            "created_at",
        ]
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
            if sub.status != HomeworkSubmission.Status.REJECTED:
                return {"id": sub.id, "status": sub.status}
        return None

    def get_timeliness_preview(self, obj):
        from .services import HomeworkService

        return {"timeliness": HomeworkService.get_timeliness(obj.due_date)}

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
        child=serializers.DictField(), required=False, default=list,
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
