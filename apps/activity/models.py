from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class ActivityEvent(models.Model):
    """Append-only record of an interaction or calculation in the system.

    One row per discrete thing that happened: a clock-in, a chore approval,
    an XP award, a drop roll, a streak update. The ``context`` JSON carries
    a ``breakdown`` list whose shape is defined in ``apps.activity.services``
    so the frontend can render intermediate math (base × multiplier = result)
    without a per-event-type React component.

    Parent-only surface (see ``apps.activity.views.ActivityEventViewSet``).
    """

    class Category(models.TextChoices):
        APPROVAL = "approval", "Approval"
        AWARD = "award", "Award"
        LEDGER = "ledger", "Ledger"
        RPG = "rpg", "RPG"
        QUEST = "quest", "Quest"
        HABIT = "habit", "Habit"
        TIMECARD = "timecard", "Timecard"
        SYSTEM = "system", "System"

    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        related_name="acted_events",
        on_delete=models.SET_NULL,
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        related_name="subject_events",
        on_delete=models.SET_NULL,
    )
    category = models.CharField(
        max_length=16, choices=Category.choices, db_index=True,
    )
    event_type = models.CharField(max_length=48, db_index=True)
    summary = models.CharField(max_length=200)

    coins_delta = models.IntegerField(null=True, blank=True)
    money_delta = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    xp_delta = models.IntegerField(null=True, blank=True)

    target_ct = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL,
    )
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    target = GenericForeignKey("target_ct", "target_id")

    context = models.JSONField(default=dict, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["subject", "-occurred_at"]),
            models.Index(fields=["category", "-occurred_at"]),
            models.Index(fields=["event_type", "-occurred_at"]),
        ]

    def __str__(self):
        who = self.subject or self.actor or "system"
        return f"{self.event_type} ({who}) @ {self.occurred_at:%Y-%m-%d %H:%M}"
