from decimal import Decimal

from django.conf import settings
from django.db import models

from config.base_models import TimestampedModel


class TimeEntry(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        VOIDED = "voided", "Voided"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="time_entries",
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="time_entries",
    )
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    auto_clocked_out = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ["-clock_in"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="active"),
                name="one_active_entry_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.project} ({self.clock_in:%Y-%m-%d})"

    def save(self, *args, **kwargs):
        if self.clock_out and self.clock_in:
            delta = self.clock_out - self.clock_in
            self.duration_minutes = int(delta.total_seconds() / 60)
        super().save(*args, **kwargs)


class Timecard(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        DISPUTED = "disputed", "Disputed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="timecards",
    )
    week_start = models.DateField()
    week_end = models.DateField()
    total_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    hourly_earnings = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    bonus_earnings = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    total_earnings = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="approved_timecards",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    parent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-week_start"]
        unique_together = [("user", "week_start")]

    def __str__(self):
        return f"{self.user} — Week of {self.week_start}"
