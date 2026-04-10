from decimal import Decimal

from django.db.models import Sum

from .models import PaymentLedger


class PaymentService:
    @staticmethod
    def get_balance(user):
        """Get the current balance for a user."""
        total = PaymentLedger.objects.filter(user=user).aggregate(
            total=Sum("amount")
        )["total"]
        return total or Decimal("0.00")

    @staticmethod
    def get_breakdown(user):
        """Get balance breakdown by entry type."""
        entries = PaymentLedger.objects.filter(user=user).values(
            "entry_type"
        ).annotate(total=Sum("amount")).order_by("entry_type")
        return {e["entry_type"]: e["total"] for e in entries}

    @staticmethod
    def record_entry(
        user,
        amount,
        entry_type,
        description="",
        *,
        project=None,
        timecard=None,
        created_by=None,
    ):
        """Single entry point for all PaymentLedger writes.

        Wrapping `PaymentLedger.objects.create` in one place makes it easy to
        audit, log, or enforce transactionality across the codebase.
        """
        return PaymentLedger.objects.create(
            user=user,
            amount=amount,
            entry_type=entry_type,
            description=description,
            project=project,
            timecard=timecard,
            created_by=created_by,
        )

    @classmethod
    def record_payout(cls, user, amount, parent_user):
        """Record a payout (Greenlight transfer)."""
        return cls.record_entry(
            user,
            -abs(amount),
            PaymentLedger.EntryType.PAYOUT,
            description=f"Greenlight payout: ${amount}",
            created_by=parent_user,
        )
