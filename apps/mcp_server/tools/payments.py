"""Payment-related MCP tools (PaymentLedger, payouts, adjustments)."""
from __future__ import annotations

from typing import Any

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.accounts.models import User

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    AdjustPaymentIn,
    GetPaymentBalanceIn,
    ListPaymentLedgerIn,
    RecordPayoutIn,
)
from ..server import tool
from ..shapes import payment_entry_to_dict, to_plain


def _resolve_target(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own payments.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@tool()
@safe_tool
def get_payment_balance(params: GetPaymentBalanceIn) -> dict[str, Any]:
    """Return monetary balance + breakdown, parallel to coin balance."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    balance = PaymentService.get_balance(target)
    breakdown = PaymentService.get_breakdown(target)
    recent = list(
        PaymentLedger.objects.filter(user=target).order_by("-created_at")[:25]
    )
    return {
        "balance": str(balance),
        "breakdown": to_plain(breakdown),
        "recent_ledger": [payment_entry_to_dict(e) for e in recent],
    }


@tool()
@safe_tool
def list_payment_ledger(params: ListPaymentLedgerIn) -> dict[str, Any]:
    """List PaymentLedger entries, optionally filtered by entry_type/since."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    qs = PaymentLedger.objects.filter(user=target)
    if params.entry_type:
        qs = qs.filter(entry_type=params.entry_type)
    if params.since:
        qs = qs.filter(created_at__date__gte=params.since)
    qs = qs.order_by("-created_at")[: params.limit]

    return {"entries": [payment_entry_to_dict(e) for e in qs]}


@tool()
@safe_tool
def record_payout(params: RecordPayoutIn) -> dict[str, Any]:
    """Record a payout to a child (parent-only).

    Wraps :meth:`PaymentService.record_payout` which writes a negative
    PaymentLedger entry tagged ``payout``.
    """
    parent = require_parent()
    try:
        child = User.objects.get(pk=params.user_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {params.user_id} not found.")

    entry = PaymentService.record_payout(child, params.amount, parent)
    if params.description:
        entry.description = params.description
        entry.save(update_fields=["description"])
    return payment_entry_to_dict(entry)


@tool()
@safe_tool
def adjust_payment(params: AdjustPaymentIn) -> dict[str, Any]:
    """Apply a positive or negative manual adjustment to a child's balance."""
    parent = require_parent()
    try:
        child = User.objects.get(pk=params.user_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {params.user_id} not found.")

    entry = PaymentService.record_entry(
        child,
        params.amount,
        PaymentLedger.EntryType.ADJUSTMENT,
        description=params.description,
        created_by=parent,
    )
    return payment_entry_to_dict(entry)
