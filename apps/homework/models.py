from decimal import Decimal

from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class HomeworkAssignment(TimestampedModel):
    class Subject(models.TextChoices):
        MATH = "math", "Math"
        READING = "reading", "Reading"
        WRITING = "writing", "Writing"
        SCIENCE = "science", "Science"
        SOCIAL_STUDIES = "social_studies", "Social Studies"
        ART = "art", "Art"
        MUSIC = "music", "Music"
        OTHER = "other", "Other"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject = models.CharField(max_length=20, choices=Subject.choices)
    effort_level = models.IntegerField(
        default=3,
        help_text="1-5 scale. Drives reward scaling via HOMEWORK_EFFORT_MULTIPLIERS.",
    )
    due_date = models.DateField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="homework_assignments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_homework",
    )
    reward_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Base money reward before effort/timeliness scaling.",
    )
    coin_reward = models.PositiveIntegerField(
        default=0,
        help_text="Base coin reward before effort/timeliness scaling.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Optional parent notes or context.")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="homework_assignments",
        help_text="Linked project for AI-planned long-form assignments.",
    )

    class Meta:
        ordering = ["due_date", "title"]

    def __str__(self):
        return f"{self.title} ({self.get_subject_display()}) — due {self.due_date}"


class HomeworkSkillTag(models.Model):
    assignment = models.ForeignKey(
        HomeworkAssignment, on_delete=models.CASCADE,
        related_name="skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill", on_delete=models.CASCADE,
    )
    xp_amount = models.PositiveIntegerField(
        default=15,
        help_text="XP awarded on approved completion.",
    )

    class Meta:
        unique_together = [("assignment", "skill")]

    def __str__(self):
        return f"{self.assignment.title} — {self.skill.name} ({self.xp_amount} XP)"


class HomeworkSubmission(CreatedAtModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Timeliness(models.TextChoices):
        EARLY = "early", "Early"
        ON_TIME = "on_time", "On Time"
        LATE = "late", "Late"
        BEYOND_CUTOFF = "beyond_cutoff", "Beyond Cutoff"

    assignment = models.ForeignKey(
        HomeworkAssignment, on_delete=models.CASCADE,
        related_name="submissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="homework_submissions",
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING,
    )
    notes = models.TextField(blank=True, help_text="Optional child submission notes.")
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="decided_homework_submissions",
    )
    reward_amount_snapshot = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Final money reward (base × effort × timeliness), frozen at submission.",
    )
    coin_reward_snapshot = models.PositiveIntegerField(
        help_text="Final coin reward (base × effort × timeliness), frozen at submission.",
    )
    timeliness = models.CharField(
        max_length=15, choices=Timeliness.choices,
        help_text="Computed at submission time by comparing submit date to due_date.",
    )
    timeliness_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2,
        help_text="Frozen multiplier (e.g., 1.25 early, 1.0 on_time, 0.5 late, 0.0 beyond).",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "user"],
                condition=~models.Q(status="rejected"),
                name="unique_active_homework_submission",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.assignment.title} ({self.status})"


class HomeworkProof(CreatedAtModel):
    submission = models.ForeignKey(
        HomeworkSubmission, on_delete=models.CASCADE,
        related_name="proofs",
    )
    image = models.ImageField(upload_to="homework_proofs/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Proof #{self.order} for {self.submission}"


class HomeworkTemplate(TimestampedModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject = models.CharField(
        max_length=20, choices=HomeworkAssignment.Subject.choices,
    )
    effort_level = models.IntegerField(default=3)
    reward_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
    )
    coin_reward = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="homework_templates",
    )
    skill_tags = models.JSONField(
        default=list, blank=True,
        help_text='[{"skill_id": 1, "xp_amount": 15}, ...] for cloning.',
    )

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"Template: {self.title} ({self.get_subject_display()})"
