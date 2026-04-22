import logging
from decimal import Decimal

from rest_framework import serializers

from apps.achievements.models import SkillCategory
from apps.achievements.serializers import SkillCategorySerializer

from .models import (
    MaterialItem, Project, ProjectCollaborator,
    ProjectMilestone, ProjectResource, ProjectStep, ProjectTemplate, SavingsGoal,
    TemplateMaterial, TemplateMilestone, TemplateResource, TemplateStep,
    User,
)

logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    google_linked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "display_name", "role", "hourly_rate", "avatar", "theme",
            "google_linked",
        ]
        read_only_fields = fields

    def get_google_linked(self, obj):
        try:
            return obj.google_account is not None
        except Exception:
            logger.debug("google_linked check failed for user %s", obj.pk, exc_info=True)
            return False


class ChildSerializer(serializers.ModelSerializer):
    google_linked = serializers.SerializerMethodField()
    age_years = serializers.IntegerField(read_only=True, allow_null=True)
    current_grade = serializers.IntegerField(read_only=True, allow_null=True)
    school_year_label = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "display_name", "role", "hourly_rate", "avatar", "theme",
            "google_linked",
            "date_of_birth", "grade_entry_year",
            "age_years", "current_grade", "school_year_label",
        ]
        read_only_fields = ["id", "username", "role", "theme", "age_years", "current_grade", "school_year_label"]

    def get_google_linked(self, obj):
        try:
            return obj.google_account is not None
        except Exception:
            logger.debug("google_linked check failed for user %s", obj.pk, exc_info=True)
            return False


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


class ProjectResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectResource
        fields = [
            "id", "project", "step", "title", "url", "resource_type", "order",
        ]


class ProjectStepSerializer(serializers.ModelSerializer):
    resources = ProjectResourceSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectStep
        fields = [
            "id", "project", "milestone", "title", "description", "order",
            "is_completed", "completed_at", "resources",
        ]
        read_only_fields = ["completed_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    category = SkillCategorySerializer(read_only=True)
    milestones_total = serializers.SerializerMethodField()
    milestones_completed = serializers.SerializerMethodField()
    steps_total = serializers.SerializerMethodField()
    steps_completed = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "title", "description", "cover_photo", "difficulty",
            "category", "status", "assigned_to", "bonus_amount", "payment_kind",
            "materials_budget", "due_date", "created_at",
            "milestones_total", "milestones_completed",
            "steps_total", "steps_completed",
        ]

    def get_milestones_total(self, obj):
        return obj.milestones.count()

    def get_milestones_completed(self, obj):
        return obj.milestones.filter(is_completed=True).count()

    def get_steps_total(self, obj):
        return obj.steps.count()

    def get_steps_completed(self, obj):
        return obj.steps.filter(is_completed=True).count()


class ProjectDetailSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    category = SkillCategorySerializer(read_only=True)
    milestones = ProjectMilestoneSerializer(many=True, read_only=True)
    materials = MaterialItemSerializer(many=True, read_only=True)
    steps = ProjectStepSerializer(many=True, read_only=True)
    resources = serializers.SerializerMethodField()

    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="assigned_to",
        write_only=True, required=False, allow_null=True,
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=SkillCategory.objects.all(), source="category",
        write_only=True, required=False, allow_null=True,
    )

    # Write-only nested creation — lets ProjectViewSet.create and the MCP tool
    # ship a fully-formed project (with steps and resources) in a single call.
    # Resources can reference a step via 0-based ``step_index`` (or null for
    # project-level); the serializer resolves it after bulk-creating steps.
    steps_create = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False,
    )
    resources_create = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False,
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
            "milestones", "materials", "steps", "resources",
            "steps_create", "resources_create",
        ]
        read_only_fields = ["created_by", "started_at", "completed_at", "xp_reward"]

    def get_resources(self, obj):
        """Return only project-level resources (step is null).

        Step-scoped resources are already nested inside each step via
        ``ProjectStepSerializer.resources``; returning them again here would
        double-count them in the client.
        """
        qs = obj.resources.filter(step__isnull=True)
        return ProjectResourceSerializer(qs, many=True).data

    def create(self, validated_data):
        steps_data = validated_data.pop("steps_create", None) or []
        resources_data = validated_data.pop("resources_create", None) or []
        project = super().create(validated_data)

        created_steps = []
        for idx, step in enumerate(steps_data):
            created_steps.append(
                ProjectStep.objects.create(
                    project=project,
                    title=step.get("title", "") or "",
                    description=step.get("description", "") or "",
                    order=step.get("order", idx),
                )
            )

        for r_idx, res in enumerate(resources_data):
            step_index = res.get("step_index")
            step_fk = None
            if step_index is not None:
                if not isinstance(step_index, int) or not (
                    0 <= step_index < len(created_steps)
                ):
                    raise serializers.ValidationError(
                        {"resources_create": f"Invalid step_index {step_index}"}
                    )
                step_fk = created_steps[step_index]
            ProjectResource.objects.create(
                project=project,
                step=step_fk,
                title=res.get("title", "") or "",
                url=res.get("url", ""),
                resource_type=res.get("resource_type", ProjectResource.ResourceType.LINK),
                order=res.get("order", r_idx),
            )

        return project


class TemplateMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateMilestone
        fields = ["id", "title", "description", "order", "bonus_amount"]


class TemplateMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateMaterial
        fields = ["id", "name", "description", "estimated_cost"]


class TemplateResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateResource
        fields = ["id", "step", "title", "url", "resource_type", "order"]


class TemplateStepSerializer(serializers.ModelSerializer):
    resources = TemplateResourceSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateStep
        fields = ["id", "milestone", "title", "description", "order", "resources"]


class ProjectTemplateSerializer(serializers.ModelSerializer):
    milestones = TemplateMilestoneSerializer(many=True, read_only=True)
    materials = TemplateMaterialSerializer(many=True, read_only=True)
    steps = TemplateStepSerializer(many=True, read_only=True)
    resources = serializers.SerializerMethodField()
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
            "milestones", "materials", "steps", "resources",
        ]
        read_only_fields = ["created_by", "created_at"]

    def get_resources(self, obj):
        qs = obj.resources.filter(step__isnull=True)
        return TemplateResourceSerializer(qs, many=True).data


class ProjectCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user", write_only=True,
    )

    class Meta:
        model = ProjectCollaborator
        fields = ["id", "project", "user", "user_id", "pay_split_percent", "joined_at"]
        read_only_fields = ["joined_at"]


class SavingsGoalSerializer(serializers.ModelSerializer):
    current_amount = serializers.SerializerMethodField()
    percent_complete = serializers.SerializerMethodField()

    class Meta:
        model = SavingsGoal
        fields = [
            "id", "title", "target_amount", "current_amount", "icon",
            "is_completed", "completed_at", "created_at", "percent_complete",
        ]
        read_only_fields = ["is_completed", "completed_at", "created_at"]

    def _balance(self, obj):
        from apps.payments.services import PaymentService
        cache = self.context.setdefault("_savings_balance_cache", {})
        if obj.user_id not in cache:
            bal = PaymentService.get_balance(obj.user) or Decimal("0")
            cache[obj.user_id] = max(bal, Decimal("0"))
        return cache[obj.user_id]

    def get_current_amount(self, obj):
        return self._balance(obj)

    def get_percent_complete(self, obj):
        if obj.target_amount <= 0:
            return 100
        pct = float(self._balance(obj) / obj.target_amount) * 100
        return min(100, round(pct))

    def to_representation(self, instance):
        # Lazy completion check: if the child's balance now covers an
        # active goal (e.g. target was lowered, or a prior write missed
        # the hook), auto-complete + run the reward pipeline on read.
        if not instance.is_completed:
            from .savings_service import SavingsGoalService
            SavingsGoalService.check_and_complete(instance.user)
            instance.refresh_from_db(fields=["is_completed", "completed_at"])
        return super().to_representation(instance)
