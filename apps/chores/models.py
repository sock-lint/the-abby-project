from decimal import Decimal

from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


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
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return f"{self.icon} {self.title}".strip()


class ChoreCompletion(CreatedAtModel):
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
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="decided_chore_completions",
    )
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
