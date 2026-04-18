"""Activity-log emission helpers.

All `ActivityEvent` writes go through ``ActivityLogService.record`` — never
inline ``ActivityEvent.objects.create(...)``. This guarantees the ``context``
payload stays conformant and that nested events inside a
``GameLoopService.on_task_completed`` call share one ``correlation_id``.

Scope semantics
---------------
``activity_scope()`` is a contextmanager backed by a ``ContextVar``. While
one is active:

* Every call to ``ActivityLogService.record`` inherits its ``correlation_id``.
* ``ledger_suppressed()`` returns True when the current scope was opened with
  ``suppress_inner_ledger=True``. ``CoinService.award_coins`` /
  ``PaymentService.record_entry`` check this so that when they're called
  from inside ``AwardService.grant`` they skip their own emission — the
  outer ``grant`` writes one consolidated ``award.*`` event with the full
  breakdown instead of a noisy pair of inner ledger rows.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Iterable, Literal, TypedDict

from django.contrib.contenttypes.models import ContentType
from django.db import models

from .models import ActivityEvent


class BreakdownStep(TypedDict, total=False):
    """One row in ``context["breakdown"]``.

    ``op`` is the glyph shown to the left of this step in the frontend strip.
    ``note`` means "purely informational, no math" and is rendered on its
    own line without an operator.
    """

    label: str
    value: Any
    op: Literal["+", "-", "×", "÷", "=", "note"]


_scope: ContextVar[dict | None] = ContextVar("activity_scope", default=None)


@contextmanager
def activity_scope(*, suppress_inner_ledger: bool = False):
    """Open a correlation scope. All nested ``record()`` calls share the UUID.

    ``suppress_inner_ledger=True`` signals that the caller (typically
    ``AwardService.grant``) will emit its own consolidated ``award.*`` event
    — the raw ``CoinLedger`` / ``PaymentLedger`` emissions inside should
    stay silent so the log isn't doubled.
    """
    parent = _scope.get()
    correlation_id = parent["correlation_id"] if parent else uuid.uuid4()
    token = _scope.set({
        "correlation_id": correlation_id,
        "suppress_inner_ledger": suppress_inner_ledger
            or (parent or {}).get("suppress_inner_ledger", False),
    })
    try:
        yield correlation_id
    finally:
        _scope.reset(token)


def current_correlation_id() -> uuid.UUID | None:
    scope = _scope.get()
    return scope["correlation_id"] if scope else None


def ledger_suppressed() -> bool:
    scope = _scope.get()
    return bool(scope and scope["suppress_inner_ledger"])


def _coerce_money(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize_breakdown(breakdown: Iterable[BreakdownStep] | None) -> list[dict]:
    if not breakdown:
        return []
    normalized: list[dict] = []
    for step in breakdown:
        if not isinstance(step, dict):
            raise TypeError(
                "activity breakdown steps must be dicts with keys "
                "{label, value, op}"
            )
        label = step.get("label")
        if not isinstance(label, str):
            raise TypeError("breakdown step.label must be a string")
        op = step.get("op", "note")
        if op not in {"+", "-", "×", "÷", "=", "note"}:
            raise ValueError(
                f"breakdown step.op must be one of +/-/×/÷/=/note, got {op!r}"
            )
        value = step.get("value")
        # Decimal isn't JSON-serializable — stringify at write time.
        if isinstance(value, Decimal):
            value = str(value)
        normalized.append({"label": label, "value": value, "op": op})
    return normalized


class ActivityLogService:
    """Single entry point for writing ActivityEvent rows."""

    @staticmethod
    def record(
        *,
        category: str,
        event_type: str,
        summary: str,
        actor=None,
        subject=None,
        target: models.Model | None = None,
        coins_delta: int | None = None,
        money_delta=None,
        xp_delta: int | None = None,
        breakdown: Iterable[BreakdownStep] | None = None,
        extras: dict | None = None,
    ) -> ActivityEvent:
        target_ct = None
        target_id = None
        if target is not None and target.pk is not None:
            target_ct = ContentType.objects.get_for_model(type(target))
            target_id = target.pk

        context = {
            "breakdown": _normalize_breakdown(breakdown),
            "extras": dict(extras) if extras else {},
        }

        return ActivityEvent.objects.create(
            actor=actor,
            subject=subject,
            category=category,
            event_type=event_type,
            summary=summary[:200],
            coins_delta=coins_delta,
            money_delta=_coerce_money(money_delta),
            xp_delta=xp_delta,
            target_ct=target_ct,
            target_id=target_id,
            context=context,
            correlation_id=current_correlation_id(),
        )
