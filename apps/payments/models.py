from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel


class PaymentLedger(CreatedAtModel):
    class EntryType(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        PROJECT_BONUS = "project_bonus", "Project Bonus"
        BOUNTY_PAYOUT = "bounty_payout", "Bounty Payout"
        MILESTONE_BONUS = "milestone_bonus", "Milestone Bonus"
        MATERIALS_REIMBURSEMENT = "materials_reimbursement", "Materials Reimbursement"
        PAYOUT = "payout", "Payout"
        ADJUSTMENT = "adjustment", "Adjustment"
        COIN_EXCHANGE = "coin_exchange", "Coin Exchange"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="payment_entries",
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    entry_type = models.CharField(max_length=25, choices=EntryType.choices)
    description = models.TextField(blank=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="payment_entries",
    )
    timecard = models.ForeignKey(
        "timecards.Timecard", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="payment_entries",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_payments",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.entry_type} — ${self.amount}"
