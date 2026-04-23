from decimal import Decimal

from django.conf import settings
from django.db import models

from config.base_models import ApprovalWorkflowModel, CreatedAtModel, TimestampedModel


class Chore(TimestampedModel):
    class Recurrence(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        ONE_TIME = "one_time", "One-Time"

    class WeekSchedule(models.TextChoices):
        EVERY_WEEK = "every_week", "Every Week"
        ALTERNATING = "alternating", "Alternating Weeks"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    reward_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
    )
    coin_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Total XP pool distributed across ChoreSkillTag rows on approval. "
            "Zero = chore awards coins/money only (legacy behaviour). "
            "Split proportionally by each tag's xp_weight."
        ),
    )
    recurrence = models.CharField(
        max_length=10, choices=Recurrence.choices, default=Recurrence.DAILY,
    )
    week_schedule = models.CharField(
        max_length=12,
        choices=WeekSchedule.choices,
        default=WeekSchedule.EVERY_WEEK,
        help_text="Controls whether this chore is active every week or alternating weeks (shared custody).",
    )
    schedule_start_date = models.DateField(
        null=True, blank=True,
        help_text="Reference date for alternating weeks. Any date during an 'on' week. "
                  "Uses ISO week parity to determine active weeks.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="assigned_chores", null=True, blank=True,
        help_text="Null = available to all children.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_chores",
    )
    is_active = models.BooleanField(default=True)
    pending_parent_review = models.BooleanField(default=False, db_index=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return f"{self.icon} {self.title}".strip()


class ChoreCompletion(ApprovalWorkflowModel, CreatedAtModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    chore = models.ForeignKey(
        Chore, on_delete=models.CASCADE, related_name="completions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="chore_completions",
    )
    completed_date = models.DateField(
        help_text="The calendar date (or period-start for weekly) this completion covers.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    notes = models.TextField(blank=True, help_text="Optional note from child.")
    reward_amount_snapshot = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Reward amount frozen at submission time.",
    )
    coin_reward_snapshot = models.PositiveIntegerField(
        help_text="Coin reward frozen at submission time.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["chore", "user", "completed_date"],
                condition=~models.Q(status="rejected"),
                name="unique_active_chore_completion_per_day",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.chore.title} ({self.status})"


class ChoreSkillTag(models.Model):
    """Declares which skills a chore rewards when approved.

    Mirrors ``ProjectSkillTag`` — XP pool from ``Chore.xp_reward`` is
    distributed proportionally by ``xp_weight`` across the linked skills.
    Added 2026-04-21 to close the life-RPG gap where duties were the one
    approval flow that fed coins/money but never the skill tree.
    """

    chore = models.ForeignKey(
        Chore, on_delete=models.CASCADE, related_name="skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill", on_delete=models.CASCADE,
    )
    xp_weight = models.IntegerField(
        default=1,
        help_text="Relative share of Chore.xp_reward this skill receives.",
    )

    class Meta:
        unique_together = [("chore", "skill")]

    def __str__(self):
        return f"{self.chore.title} — {self.skill.name} ({self.xp_weight}x)"
