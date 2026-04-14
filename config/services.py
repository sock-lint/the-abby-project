from django.db.models import Sum
from django.utils import timezone


def finalize_decision(instance, new_status, parent, notes=""):
    """Stamp approval/denial fields on a pending-decision model instance.

    Writes ``status``, ``decided_at``, ``decided_by``. If the model also has
    a ``parent_notes`` field and ``notes`` is truthy, writes that too.
    Works across the approval-workflow models (ChoreCompletion,
    HomeworkSubmission, RewardRedemption, ExchangeRequest).
    """
    instance.status = new_status
    instance.decided_at = timezone.now()
    instance.decided_by = parent
    update_fields = ["status", "decided_at", "decided_by"]
    if notes and any(f.name == "parent_notes" for f in instance._meta.fields):
        instance.parent_notes = notes
        update_fields.append("parent_notes")
    instance.save(update_fields=update_fields)


class BaseLedgerService:
    """Base class for append-only ledger services (PaymentLedger, CoinLedger).

    Subclasses must set:
        ledger_model   - the Django model class
        category_field - the field name used for breakdown grouping
        default_value  - zero value for balance (Decimal("0.00") or 0)
    """

    ledger_model = None
    category_field = None
    default_value = 0

    @classmethod
    def get_balance(cls, user):
        total = cls.ledger_model.objects.filter(user=user).aggregate(
            total=Sum("amount"),
        )["total"]
        return type(cls.default_value)(total or cls.default_value)

    @classmethod
    def get_breakdown(cls, user):
        entries = (
            cls.ledger_model.objects.filter(user=user)
            .values(cls.category_field)
            .annotate(total=Sum("amount"))
            .order_by(cls.category_field)
        )
        default = cls.default_value
        return {
            e[cls.category_field]: type(default)(e["total"] or default)
            for e in entries
        }
