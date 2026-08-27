"""Monthly filament + print-time budget accounting.

Two dimensions, one ledger. See the docstring on
:class:`apps.printing.models.PrintBudgetLedger` for why this doesn't
subclass ``config.services.BaseLedgerService``.

Where the numbers come from
---------------------------
The Bambu MQTT report does **not** carry consumed filament mass. It reports
progress, layers and remaining time; the AMS reports a per-tray ``remain``
percentage, which is a coarse spool gauge, not a per-job consumption figure.
So grams cannot be observed — they are *estimated*, by the parent, from the
slicer, at approval time, and stored on
``PrintRequest.estimated_grams``. That is the number this module debits.
Minutes, by contrast, ARE observed: we debit the job's real wall-clock
duration.

A failed print gets a proportional grams debit (filament really was used up
to the failure point) floored at
:data:`apps.printing.constants.FAILED_PRINT_MIN_FRACTION`, because a print
that dies on layer 1 still burned a purge line and a skirt.
"""
from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from .constants import FAILED_PRINT_MIN_FRACTION
from .models import PrintBudget, PrintBudgetLedger

#: Remaining fraction at or below which we warn the household.
LOW_BUDGET_FRACTION = 0.2

ZERO = Decimal("0.00")


def month_start(day: datetime.date | None = None) -> datetime.date:
    """First day of the local (``America/Phoenix``) month containing ``day``.

    Uses ``timezone.localdate()`` rather than ``date.today()`` /
    ``timezone.now().date()`` for the same reason the chronicle services do:
    a print that finishes at 6pm Phoenix on the 31st is UTC-tomorrow, and a
    naive UTC date would bill it to next month.
    """
    if day is None:
        day = timezone.localdate()
    return day.replace(day=1)


def quantize_grams(value) -> Decimal:
    """Coerce anything number-ish to a 2dp Decimal of grams."""
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


#: Terse alias used throughout this module.
_q = quantize_grams


class PrintBudgetService:
    """Read + write the two-dimensional monthly budget."""

    @staticmethod
    def get_budget(user) -> PrintBudget:
        budget, _ = PrintBudget.objects.get_or_create(user=user)
        return budget

    @staticmethod
    def get_usage(user, month: datetime.date | None = None) -> dict:
        """Summed grams + minutes consumed in ``month`` (defaults to now)."""
        totals = PrintBudgetLedger.objects.filter(
            user=user, period_month=month_start(month),
        ).aggregate(grams=Sum("grams"), minutes=Sum("minutes"))
        return {
            "grams": _q(totals["grams"]),
            "minutes": int(totals["minutes"] or 0),
        }

    @classmethod
    def get_remaining(cls, user, month: datetime.date | None = None) -> dict:
        """Remaining allowance. ``None`` on a dimension means "no cap".

        Remaining can go negative — a parent may approve past the cap with
        ``force``, and an actual print can overshoot its estimate. Clamping
        to zero would hide that, so we don't.
        """
        budget = cls.get_budget(user)
        usage = cls.get_usage(user, month)
        enforced = budget.is_active
        grams_cap = budget.grams_per_month if enforced else None
        minutes_cap = budget.minutes_per_month if enforced else None
        return {
            "grams": None if grams_cap is None else _q(grams_cap) - usage["grams"],
            "minutes": None if minutes_cap is None else int(minutes_cap) - usage["minutes"],
        }

    @classmethod
    def summary(cls, user, month: datetime.date | None = None) -> dict:
        """The payload the Forge budget panel renders."""
        budget = cls.get_budget(user)
        period = month_start(month)
        usage = cls.get_usage(user, period)
        remaining = cls.get_remaining(user, period)
        return {
            "period_month": period.isoformat(),
            "is_active": budget.is_active,
            "grams_per_month": (
                None if budget.grams_per_month is None else _q(budget.grams_per_month)
            ),
            "minutes_per_month": budget.minutes_per_month,
            "grams_used": usage["grams"],
            "minutes_used": usage["minutes"],
            "grams_remaining": remaining["grams"],
            "minutes_remaining": remaining["minutes"],
            "notes": budget.notes,
        }

    @classmethod
    def check_affordable(cls, user, *, grams=None, minutes=None,
                         month: datetime.date | None = None) -> list[str]:
        """Return a list of human-readable overage reasons (empty = fits).

        Callers decide whether an overage blocks (approval, by default) or
        merely warns (close-out, always — the filament is already spent).
        """
        remaining = cls.get_remaining(user, month)
        problems: list[str] = []
        if grams is not None and remaining["grams"] is not None:
            want = _q(grams)
            if want > remaining["grams"]:
                problems.append(
                    f"needs {want}g but only {remaining['grams']}g of filament "
                    f"is left this month",
                )
        if minutes is not None and remaining["minutes"] is not None:
            if int(minutes) > remaining["minutes"]:
                problems.append(
                    f"needs {int(minutes)} min but only {remaining['minutes']} min "
                    f"of print time is left this month",
                )
        return problems

    @classmethod
    def record(cls, user, *, grams=ZERO, minutes=0, reason, request=None, job=None,
               note="", recorded_by=None, month: datetime.date | None = None):
        """Append one ledger row. Positive consumes, negative returns."""
        entry = PrintBudgetLedger.objects.create(
            user=user,
            request=request,
            job=job,
            period_month=month_start(month),
            grams=_q(grams),
            minutes=int(minutes or 0),
            reason=reason,
            note=note[:200],
            recorded_by=recorded_by,
        )
        from apps.activity.services import ActivityLogService

        ActivityLogService.record(
            category="ledger",
            event_type=f"print.budget.{reason}",
            summary=f"Print budget: {entry.grams}g / {entry.minutes} min ({reason})",
            subject=user,
            actor=recorded_by,
            target=entry,
            breakdown=[
                {"label": "Filament", "value": f"{entry.grams} g", "op": "-"},
                {"label": "Print time", "value": f"{entry.minutes} min", "op": "-"},
            ],
            extras={"reason": reason, "request_id": request.pk if request else None},
        )
        return entry

    @staticmethod
    def grams_for_failed_print(estimated_grams, layer_num, total_layer_num) -> Decimal:
        """Proportional filament debit for a print that didn't finish.

        ``layers_done / total_layers``, floored at
        ``FAILED_PRINT_MIN_FRACTION`` so an early failure still costs
        something (purge + skirt are real filament), and capped at 1.0. When
        the report never gave us a layer count we fall back to the floor
        rather than debiting the whole estimate — the household shouldn't
        eat a full spool's worth of budget for a print we couldn't measure.
        """
        estimate = _q(estimated_grams)
        if estimate <= ZERO:
            return ZERO
        if total_layer_num and total_layer_num > 0:
            fraction = min(1.0, max(FAILED_PRINT_MIN_FRACTION,
                                    (layer_num or 0) / total_layer_num))
        else:
            fraction = FAILED_PRINT_MIN_FRACTION
        return _q(estimate * Decimal(str(fraction)))

    @classmethod
    def is_low(cls, user, month: datetime.date | None = None) -> bool:
        """True when either capped dimension has dropped to the warn threshold."""
        budget = cls.get_budget(user)
        if not budget.is_active:
            return False
        remaining = cls.get_remaining(user, month)
        if budget.grams_per_month:
            cap = Decimal(budget.grams_per_month)
            if cap > 0 and remaining["grams"] is not None:
                if remaining["grams"] <= cap * Decimal(str(LOW_BUDGET_FRACTION)):
                    return True
        if budget.minutes_per_month:
            cap_min = int(budget.minutes_per_month)
            if cap_min > 0 and remaining["minutes"] is not None:
                if remaining["minutes"] <= cap_min * LOW_BUDGET_FRACTION:
                    return True
        return False
