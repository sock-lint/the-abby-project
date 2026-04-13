import logging
from decimal import Decimal

from config.services import BaseLedgerService

from .models import PaymentLedger

logger = logging.getLogger(__name__)


class PaymentService(BaseLedgerService):
    ledger_model = PaymentLedger
    category_field = "entry_type"
    default_value = Decimal("0.00")

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
