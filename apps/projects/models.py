import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        PARENT = "parent", "Parent"
        CHILD = "child", "Child"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CHILD)
    hourly_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("8.00")
    )
    display_name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    theme = models.CharField(
        max_length=20, default="summer",
        choices=[
            ("summer", "Summer"),
            ("winter", "Winter Break"),
            ("spring", "Spring Break"),
            ("autumn", "Autumn"),
        ],
    )

    objects = CustomUserManager()

    def __str__(self):
        return self.display_name or self.username


class SkillCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default="#D97706")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "skill categories"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}"


class Project(models.Model):
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
        SkillCategory, on_delete=models.SET_NULL, null=True, blank=True,
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        TIMECARD_READY = "timecard_ready", "Timecard Ready"
        TIMECARD_APPROVED = "timecard_approved", "Timecard Approved"
        BADGE_EARNED = "badge_earned", "Badge Earned"
        PROJECT_APPROVED = "project_approved", "Project Approved"
        PROJECT_CHANGES = "project_changes", "Changes Requested"
        PAYOUT_RECORDED = "payout_recorded", "Payout Recorded"
        SKILL_UNLOCKED = "skill_unlocked", "Skill Unlocked"
        MILESTONE_COMPLETED = "milestone_completed", "Milestone Completed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    notification_type = models.CharField(
        max_length=25, choices=NotificationType.choices
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.title}"


class ProjectTemplate(models.Model):
    """A reusable project template created from a completed project."""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructables_url = models.URLField(blank=True, null=True)
    difficulty = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 6)], default=1
    )
    category = models.ForeignKey(
        SkillCategory, on_delete=models.SET_NULL, null=True, blank=True,
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
    created_at = models.DateTimeField(auto_now_add=True)

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


class SavingsGoal(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.title} (${self.current_amount}/${self.target_amount})"

    @property
    def percent_complete(self):
        if self.target_amount <= 0:
            return 100
        return min(100, round(float(self.current_amount / self.target_amount) * 100))


class ProjectIngestionJob(models.Model):
    """Staging row for project auto-ingestion from a URL or uploaded file.

    A job is created when a parent submits a source; a Celery task runs the
    matching ingestor and stores the result in ``result_json``. The parent then
    reviews/edits the staged draft and commits it, which creates the real
    ``Project`` row plus its milestones and materials.
    """

    class SourceType(models.TextChoices):
        INSTRUCTABLES = "instructables", "Instructables"
        URL = "url", "Generic URL"
        PDF = "pdf", "PDF Upload"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        DISCARDED = "discarded", "Discarded"
        COMMITTED = "committed", "Committed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="ingestion_jobs",
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_url = models.URLField(blank=True, null=True, max_length=1000)
    source_file = models.FileField(
        upload_to="ingestion/", blank=True, null=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    result_json = models.JSONField(blank=True, null=True)
    error = models.TextField(blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingestion_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"IngestionJob {self.id} ({self.status})"
