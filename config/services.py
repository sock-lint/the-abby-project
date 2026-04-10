from django.db.models import Sum


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
