from rest_framework import serializers

from .models import (
    MaterialItem, Notification, Project, ProjectCollaborator, ProjectIngestionJob,
    ProjectMilestone, ProjectTemplate, SavingsGoal, SkillCategory, TemplateMaterial,
    TemplateMilestone, User,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "display_name", "role", "hourly_rate", "avatar", "theme",
        ]
        read_only_fields = fields


class SkillCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillCategory
        fields = ["id", "name", "icon", "color", "description"]


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id", "project", "title", "description", "order",
            "is_completed", "completed_at", "bonus_amount",
        ]
        read_only_fields = ["completed_at"]


class MaterialItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialItem
        fields = [
            "id", "project", "name", "description", "estimated_cost",
            "actual_cost", "is_purchased", "purchased_at", "receipt_photo",
            "reimbursed",
        ]
        read_only_fields = ["purchased_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    category = SkillCategorySerializer(read_only=True)
    milestones_total = serializers.SerializerMethodField()
    milestones_completed = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "title", "description", "cover_photo", "difficulty",
            "category", "status", "assigned_to", "bonus_amount", "payment_kind",
            "materials_budget", "due_date", "created_at",
            "milestones_total", "milestones_completed",
        ]

    def get_milestones_total(self, obj):
        return obj.milestones.count()

    def get_milestones_completed(self, obj):
        return obj.milestones.filter(is_completed=True).count()


class ProjectDetailSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    category = SkillCategorySerializer(read_only=True)
    milestones = ProjectMilestoneSerializer(many=True, read_only=True)
    materials = MaterialItemSerializer(many=True, read_only=True)

    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="assigned_to",
        write_only=True, required=False, allow_null=True,
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=SkillCategory.objects.all(), source="category",
        write_only=True, required=False, allow_null=True,
    )

    class Meta:
        model = Project
        fields = [
            "id", "title", "description", "cover_photo", "instructables_url",
            "difficulty", "category", "category_id", "status",
            "assigned_to", "assigned_to_id", "created_by",
            "bonus_amount", "payment_kind", "hourly_rate_override", "materials_budget",
            "due_date", "started_at", "completed_at", "xp_reward",
            "parent_notes", "created_at", "updated_at",
            "milestones", "materials",
        ]
        read_only_fields = ["created_by", "started_at", "completed_at", "xp_reward"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "notification_type", "is_read", "created_at"]
        read_only_fields = ["title", "message", "notification_type", "created_at"]


class TemplateMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateMilestone
        fields = ["id", "title", "description", "order", "bonus_amount"]


class TemplateMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateMaterial
        fields = ["id", "name", "description", "estimated_cost"]


class ProjectTemplateSerializer(serializers.ModelSerializer):
    milestones = TemplateMilestoneSerializer(many=True, read_only=True)
    materials = TemplateMaterialSerializer(many=True, read_only=True)
    category = SkillCategorySerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=SkillCategory.objects.all(), source="category",
        write_only=True, required=False, allow_null=True,
    )

    class Meta:
        model = ProjectTemplate
        fields = [
            "id", "title", "description", "instructables_url", "difficulty",
            "category", "category_id", "bonus_amount", "materials_budget",
            "source_project", "created_by", "is_public", "created_at",
            "milestones", "materials",
        ]
        read_only_fields = ["created_by", "created_at"]


class ProjectCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user", write_only=True,
    )

    class Meta:
        model = ProjectCollaborator
        fields = ["id", "project", "user", "user_id", "pay_split_percent", "joined_at"]
        read_only_fields = ["joined_at"]


class ProjectIngestionJobSerializer(serializers.ModelSerializer):
    """Read/write serializer for the ingest staging job.

    ``result_json`` is writable so the parent can edit the staged draft from
    the preview screen before committing.
    """

    class Meta:
        model = ProjectIngestionJob
        fields = [
            "id", "source_type", "source_url", "source_file", "status",
            "result_json", "error", "project", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "error", "project", "created_at", "updated_at",
        ]


class SavingsGoalSerializer(serializers.ModelSerializer):
    percent_complete = serializers.ReadOnlyField()

    class Meta:
        model = SavingsGoal
        fields = [
            "id", "title", "target_amount", "current_amount", "icon",
            "is_completed", "completed_at", "created_at", "percent_complete",
        ]
        read_only_fields = ["is_completed", "completed_at", "created_at"]
