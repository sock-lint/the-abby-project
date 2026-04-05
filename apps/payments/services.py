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
    def record_payout(user, amount, parent_user):
        """Record a payout (Greenlight transfer)."""
        return PaymentLedger.objects.create(
            user=user,
            amount=-abs(amount),
            entry_type="payout",
            description=f"Greenlight payout: ${amount}",
            created_by=parent_user,
        )
