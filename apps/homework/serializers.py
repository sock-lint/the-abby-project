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
    user_name = serializers.SerializerMethodField()
    reward_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id", "assignment", "assignment_title", "assignment_subject",
            "user", "user_name",
            "status", "notes",
            "decided_at", "decided_by",
            "reward_amount_snapshot", "coin_reward_snapshot",
            "timeliness", "timeliness_multiplier",
            "proofs", "reward_breakdown",
            "created_at",
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.display_name or obj.user.username

    def get_reward_breakdown(self, obj):
        return {
            "base_money": str(obj.assignment.reward_amount),
            "base_coins": obj.assignment.coin_reward,
            "effort_level": obj.assignment.effort_level,
            "timeliness": obj.timeliness,
            "timeliness_multiplier": str(obj.timeliness_multiplier),
            "final_money": str(obj.reward_amount_snapshot),
            "final_coins": obj.coin_reward_snapshot,
        }


class HomeworkAssignmentSerializer(serializers.ModelSerializer):
    skill_tags = HomeworkSkillTagSerializer(many=True, read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    submission_status = serializers.SerializerMethodField()
    timeliness_preview = serializers.SerializerMethodField()
    has_project = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "subject",
            "effort_level", "due_date",
            "assigned_to", "assigned_to_name",
            "created_by", "created_by_name",
            "reward_amount", "coin_reward",
            "is_active", "notes",
            "project", "has_project",
            "skill_tags",
            "submission_status", "timeliness_preview",
            "created_at", "updated_at",
        ]

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.display_name or obj.assigned_to.username

    def get_created_by_name(self, obj):
        return obj.created_by.display_name or obj.created_by.username

    def get_submission_status(self, obj):
        sub = obj.submissions.exclude(
            status=HomeworkSubmission.Status.REJECTED,
        ).first()
        if sub:
            return {"id": sub.id, "status": sub.status}
        return None

    def get_timeliness_preview(self, obj):
        from .services import HomeworkService

        label, mult = HomeworkService.get_timeliness(obj.due_date)
        return {"timeliness": label, "multiplier": str(mult)}

    def get_has_project(self, obj):
        return obj.project_id is not None


class HomeworkAssignmentWriteSerializer(serializers.ModelSerializer):
    skill_tags = serializers.ListField(
        child=serializers.DictField(), required=False, default=list,
    )

    class Meta:
        model = HomeworkAssignment
        fields = [
            "title", "description", "subject",
            "effort_level", "due_date",
            "assigned_to", "reward_amount", "coin_reward",
            "notes", "skill_tags",
        ]

    def validate_effort_level(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Effort level must be between 1 and 5.")
        return value


class HomeworkTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeworkTemplate
        fields = [
            "id", "title", "description", "subject",
            "effort_level", "reward_amount", "coin_reward",
            "skill_tags", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
