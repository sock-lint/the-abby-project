"""Daily affirmation, retained short notes, and the daily writing Coin allowance.

Today now opens the Chronicle journal. These rows retain earlier clients'
private gratitude lines and the deterministic affirmation. ``coin_paid_at``
prevents both writing endpoints from paying the same daily allowance twice.
Earlier notes also have a private Chronicle history projection, without
retroactive journal XP or game progress.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from config.base_models import TimestampedModel


class DailyWellbeingEntry(TimestampedModel):
    """One row per (user, local-date) — the kid's daily wellbeing snapshot."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wellbeing_entries",
    )
    date = models.DateField(db_index=True)
    affirmation_slug = models.CharField(
        max_length=80,
        help_text=(
            "Slug of the affirmation pulled from content/wellbeing/affirmations.yaml. "
            "Stored as a slug rather than the full text so editing the YAML "
            "doesn't drift past entries — they re-resolve to the new copy."
        ),
    )
    gratitude_lines = models.JSONField(
        default=list, blank=True,
        help_text=(
            "Up to 3 short gratitude entries the kid wrote. Empty list "
            "until the first submit. Each entry is a plain string ≤200 "
            "chars; validated by the service layer."
        ),
    )
    coin_paid_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "Timestamp of the first-of-day gratitude coin payout. Subsequent "
            "edits on the same row don't repay the coin trickle — this field "
            "is the idempotency key."
        ),
    )

    class Meta:
        ordering = ["-date"]
        unique_together = [("user", "date")]
        verbose_name_plural = "daily wellbeing entries"

    def __str__(self):
        lines = len(self.gratitude_lines or [])
        return f"{self.user} · {self.date} · {lines} gratitude line(s)"
