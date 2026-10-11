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
        CHORE_REWARD = "chore_reward", "Chore Reward"
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


class GreenlightTransfer(CreatedAtModel):
    """Parent-confirmed external transfer; the linked ledger row settles debt."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual confirmation"
        STATEMENT = "statement", "Statement reconciliation"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment_entry = models.OneToOneField(
        PaymentLedger, on_delete=models.CASCADE, related_name="greenlight_transfer",
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    transferred_on = models.DateField()
    reference = models.CharField(max_length=200, blank=True)
    memo = models.CharField(max_length=1000, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices)
    idempotency_key = models.CharField(max_length=128)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="confirmed_greenlight_transfers",
    )

    class Meta:
        ordering = ["-transferred_on", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="greenlight_transfer_user_key"),
            models.UniqueConstraint(
                fields=["user", "reference"], condition=~models.Q(reference=""),
                name="greenlight_transfer_user_reference",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="greenlight_transfer_positive"),
        ]


class GreenlightBalanceSnapshot(CreatedAtModel):
    """Reported account balance as of a date; never inferred from transfers."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    as_of = models.DateTimeField()
    memo = models.CharField(max_length=1000, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="recorded_greenlight_balances",
    )

    class Meta:
        ordering = ["-as_of", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="greenlight_balance_nonnegative"),
        ]


class GreenlightStatementTransfer(CreatedAtModel):
    """One selected statement transfer matched to exactly one confirmed payout."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fingerprint = models.CharField(max_length=64)
    transfer = models.OneToOneField(
        GreenlightTransfer, on_delete=models.CASCADE, related_name="statement_row",
    )
    transferred_on = models.DateField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.CharField(max_length=1000, blank=True)
    reference = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="reconciled_greenlight_rows",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "fingerprint"], name="greenlight_statement_user_fingerprint"),
        ]
