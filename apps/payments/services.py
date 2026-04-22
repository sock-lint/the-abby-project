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
        entry = PaymentLedger.objects.create(
            user=user,
            amount=amount,
            entry_type=entry_type,
            description=description,
            project=project,
            timecard=timecard,
            created_by=created_by,
        )
        from apps.activity.services import ActivityLogService, ledger_suppressed

        if not ledger_suppressed():
            ActivityLogService.record(
                category="ledger",
                event_type=f"ledger.money.{entry_type}",
                summary=description
                    or f"Money ${amount} ({entry_type})",
                actor=created_by,
                subject=user,
                target=entry,
                money_delta=amount,
                breakdown=[
                    {"label": entry_type, "value": str(amount), "op": "="},
                ],
                extras={
                    "entry_type": entry_type,
                    "description": description or "",
                    "project_id": project.pk if project else None,
                    "timecard_id": timecard.pk if timecard else None,
                },
            )

        # Trigger savings-goal completion for any goal whose target the
        # child's new balance now covers. Wrapped + logged — a failure
        # downstream (badge evaluation, notifications) must never roll
        # back the ledger entry itself.
        try:
            from apps.projects.savings_service import SavingsGoalService
            SavingsGoalService.check_and_complete(user)
        except Exception:
            logger.exception(
                "Savings-goal completion check failed for user %s "
                "after PaymentLedger write %s", user.pk, entry.pk,
            )

        return entry

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
