from django.db.models import Sum
from django.utils import timezone


def bump_daily_counter(counter_model, user, day):
    """Read-modify-write a per-user per-day counter under a row lock.

    Returns the PRE-increment count so callers can gate on the old value
    (i.e. the first call for a given day returns 0, the second 1, etc.).

    The lock is required so two concurrent calls from the same user can't
    both read 0 and both fire downstream rewards. Counter rows survive
    parent-row deletes — that's the point of the anti-farm gate, since a
    create→delete→create cycle still observes the row.

    ``counter_model`` is any concrete subclass of
    :class:`config.base_models.DailyCounterModel`.
    """
    counter, _ = counter_model.objects.select_for_update().get_or_create(
        user=user, occurred_on=day, defaults={"count": 0},
    )
    prior = counter.count
    counter.count = prior + 1
    counter.save(update_fields=["count"])
    return prior


def finalize_decision(instance, new_status, parent, notes="", *,
                      activity_category=None, activity_event_type=None,
                      activity_summary=None, activity_subject=None,
                      activity_extras=None):
    """Stamp approval/denial fields on a pending-decision model instance.

    Writes ``status``, ``decided_at``, ``decided_by``. If the model also has
    a ``parent_notes`` field and ``notes`` is truthy, writes that too.
    Works across the approval-workflow models (ChoreCompletion,
    HomeworkSubmission, RewardRedemption, ExchangeRequest).

    When the caller passes ``activity_event_type``, an ``ActivityEvent`` is
    also recorded with ``actor=parent``, ``subject=activity_subject``
    (defaults to ``instance.user``), and ``target=instance``. The domain
    service is still free to emit its own richer events; this hook is for
    call sites that want one line of plumbing instead of two.
    """
    instance.status = new_status
    instance.decided_at = timezone.now()
    instance.decided_by = parent
    update_fields = ["status", "decided_at", "decided_by"]
    if notes and any(f.name == "parent_notes" for f in instance._meta.fields):
        instance.parent_notes = notes
        update_fields.append("parent_notes")
    instance.save(update_fields=update_fields)

    if activity_event_type:
        from apps.activity.services import ActivityLogService

        subject = activity_subject
        if subject is None and hasattr(instance, "user"):
            subject = instance.user
        ActivityLogService.record(
            category=activity_category or "approval",
            event_type=activity_event_type,
            summary=activity_summary
                or f"{new_status.title()}: {instance}"[:200],
            actor=parent,
            subject=subject,
            target=instance,
            extras={
                "status": new_status,
                "parent_notes": notes or None,
                **(activity_extras or {}),
            },
        )


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
    def get_positive_total(cls, user):
        """Sum lifetime positive-amount entries (lifetime "earned").

        Excludes spends, refunds, and any other negative entries. Shared by
        badge criteria (TOTAL_EARNED / TOTAL_COINS_EARNED) so the definition
        of "lifetime earned" lives in one place across PaymentLedger and
        CoinLedger.
        """
        total = cls.ledger_model.objects.filter(
            user=user, amount__gt=0,
        ).aggregate(total=Sum("amount"))["total"]
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
