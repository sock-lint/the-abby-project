"""Shared abstract model bases.

Abstract models don't need to live inside an installed app; they just need to
be importable wherever concrete models inherit from them.
"""
from django.conf import settings
from django.db import models


class CreatedAtModel(models.Model):
    """Adds an auto-populated ``created_at`` timestamp."""

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class TimestampedModel(CreatedAtModel):
    """Adds both ``created_at`` (immutable) and ``updated_at`` (auto-updated)."""

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DailyCounterModel(models.Model):
    """Abstract base for per-user per-day anti-farm counters.

    Subclasses persist a small row (user, occurred_on, count) that survives
    deletes of the entity they're gating, so a child + cooperating parent
    can't farm rewards by create→delete→create within the same local day.
    Use :func:`config.services.bump_daily_counter` to increment under a
    row lock.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )
    occurred_on = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        unique_together = [("user", "occurred_on")]
        indexes = [models.Index(fields=["user", "occurred_on"])]


class ApprovalWorkflowModel(models.Model):
    """Shared audit fields for submit-then-approve workflow models.

    Used by ChoreCompletion, HomeworkSubmission, RewardRedemption, and
    ExchangeRequest. Subclasses define their own ``status`` field with
    app-specific ``Status`` choices, and (optionally) ``parent_notes``.

    Subclasses must set ``related_name`` on ``decided_by`` via the model Meta
    or inline — otherwise Django's default reverse accessor will collide.
    Preserve the current ``related_name`` to avoid migration churn.
    """

    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        abstract = True
