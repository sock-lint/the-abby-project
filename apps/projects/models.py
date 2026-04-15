from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.accounts.models import User  # noqa: F401  — re-exported for historical imports

from config.base_models import CreatedAtModel, TimestampedModel


class Project(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    class PaymentKind(models.TextChoices):
        REQUIRED = "required", "Required (allowance)"
        BOUNTY = "bounty", "Bounty (up for grabs)"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cover_photo = models.ImageField(upload_to="projects/covers/", blank=True, null=True)
    instructables_url = models.URLField(blank=True, null=True)
    difficulty = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 6)], default=1
    )
    category = models.ForeignKey(
        "achievements.SkillCategory", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="projects",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="assigned_projects", null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_projects",
    )
    bonus_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    payment_kind = models.CharField(
        max_length=10, choices=PaymentKind.choices, default=PaymentKind.REQUIRED,
        help_text="Required projects are part of normal allowance; bounty projects are up-for-grabs with a cash reward.",
    )
    hourly_rate_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    materials_budget = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    xp_reward = models.PositiveIntegerField(default=0)
    parent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.xp_reward:
            self.xp_reward = 50 * self.difficulty
        super().save(*args, **kwargs)


class ProjectMilestone(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="milestones"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    bonus_amount = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.project.title} — {self.title}"


class MaterialItem(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="materials"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    estimated_cost = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    actual_cost = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    is_purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)
    receipt_photo = models.ImageField(
        upload_to="receipts/", blank=True, null=True
    )
    reimbursed = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.project.title})"


class ProjectStep(TimestampedModel):
    """An ordered walkthrough instruction for a project.

    Distinct from ``ProjectMilestone`` (which is goal-based with an optional
    ``bonus_amount`` tied to the ledger). Steps are purely instructional —
    completing one just marks progress; no coins, no XP, no payments.

    Steps may optionally belong to a ``ProjectMilestone`` (chapter / phase),
    in which case the UI groups them under that milestone with a progress
    rollup. Steps with ``milestone=None`` are "loose" — rendered in an "Other
    Steps" bucket. Deleting a milestone un-groups its steps via SET_NULL
    rather than cascading.
    """
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="steps"
    )
    milestone = models.ForeignKey(
        ProjectMilestone, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="steps",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.project.title} — Step {self.order + 1}: {self.title}"


class ProjectResource(TimestampedModel):
    """A reference link (video, doc, inspiration URL) for a project or step.

    If ``step`` is set, the resource is displayed inline under that step. If
    ``step`` is null, the resource is a project-level reference shown in the
    Overview tab.
    """
    class ResourceType(models.TextChoices):
        LINK = "link", "Link"
        VIDEO = "video", "Video"
        DOC = "doc", "Document"
        IMAGE = "image", "Image"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="resources"
    )
    step = models.ForeignKey(
        ProjectStep, on_delete=models.CASCADE, related_name="resources",
        null=True, blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=1000)
    resource_type = models.CharField(
        max_length=10, choices=ResourceType.choices, default=ResourceType.LINK,
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["step_id", "order", "id"]

    def __str__(self):
        label = self.title or self.url
        return f"{self.project.title} — {label}"


class ProjectTemplate(CreatedAtModel):
    """A reusable project template created from a completed project."""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructables_url = models.URLField(blank=True, null=True)
    difficulty = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 6)], default=1
    )
    category = models.ForeignKey(
        "achievements.SkillCategory", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="templates",
    )
    bonus_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    materials_budget = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    source_project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="templates_created",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_templates",
    )
    is_public = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Template: {self.title}"


class TemplateMilestone(models.Model):
    template = models.ForeignKey(
        ProjectTemplate, on_delete=models.CASCADE, related_name="milestones"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    bonus_amount = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.template.title} — {self.title}"


class TemplateMaterial(models.Model):
    template = models.ForeignKey(
        ProjectTemplate, on_delete=models.CASCADE, related_name="materials"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    estimated_cost = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.template.title})"


class TemplateStep(models.Model):
    template = models.ForeignKey(
        ProjectTemplate, on_delete=models.CASCADE, related_name="steps"
    )
    milestone = models.ForeignKey(
        TemplateMilestone, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="steps",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.template.title} — Step {self.order + 1}: {self.title}"


class TemplateResource(models.Model):
    template = models.ForeignKey(
        ProjectTemplate, on_delete=models.CASCADE, related_name="resources"
    )
    step = models.ForeignKey(
        TemplateStep, on_delete=models.CASCADE, related_name="resources",
        null=True, blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=1000)
    resource_type = models.CharField(
        max_length=10,
        choices=ProjectResource.ResourceType.choices,
        default=ProjectResource.ResourceType.LINK,
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["step_id", "order", "id"]

    def __str__(self):
        label = self.title or self.url
        return f"{self.template.title} — {label}"


class ProjectCollaborator(models.Model):
    """Tracks additional children assigned to a collaborative project."""
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="collaborators"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="collaborated_projects",
    )
    pay_split_percent = models.IntegerField(default=50)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "user")]

    def __str__(self):
        return f"{self.user} on {self.project.title} ({self.pay_split_percent}%)"


class SavingsGoal(CreatedAtModel):
    """A savings target set by the child."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="savings_goals",
    )
    title = models.CharField(max_length=200)
    target_amount = models.DecimalField(max_digits=8, decimal_places=2)
    current_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    icon = models.CharField(max_length=50, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.title} (${self.current_amount}/${self.target_amount})"

    @property
    def percent_complete(self):
        if self.target_amount <= 0:
            return 100
        return min(100, round(float(self.current_amount / self.target_amount) * 100))


