"""Payment-related MCP tools (PaymentLedger, payouts, adjustments)."""
from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.payments.greenlight import confirm_transfer
from apps.payments.models import PaymentLedger
from apps.payments.serializers import GreenlightPayoutSerializer
from apps.payments.services import PaymentService

from ..context import (
    get_current_user, require_parent,
    resolve_child_in_family, resolve_target_user,
)
from ..errors import MCPValidationError, safe_tool
from ..pagination import paginate_created_history
from ..schemas import (
    AdjustPaymentIn,
    GetPaymentBalanceIn,
    ListPaymentLedgerIn,
    RecordPayoutIn,
)
from ..server import tool
from ..retries import mutation_once
from ..shapes import payment_entry_to_dict, to_plain


@tool()
@safe_tool
def get_payment_balance(params: GetPaymentBalanceIn) -> dict[str, Any]:
    """Return money still owed to a child, breakdown and recent entries."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

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
    """Read scoped payment history, optionally filtered by entry_type/since.

    Follow ``next_cursor`` with the same filters for older entries. ``total``
    counts this target's matching history inside the initial page boundary.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

    qs = PaymentLedger.objects.filter(user=target)
    if params.entry_type:
        qs = qs.filter(entry_type=params.entry_type)
    if params.since:
        qs = qs.filter(created_at__date__gte=params.since)
    entries, page = paginate_created_history(
        qs, actor=user, tool="list_payment_ledger",
        filters={
            "user_id": target.pk, "entry_type": params.entry_type,
            "since": params.since.isoformat() if params.since else None,
            "timezone": timezone.get_current_timezone_name(),
        },
        limit=params.limit, cursor=params.cursor,
    )
    return {"entries": [payment_entry_to_dict(e) for e in entries], **page}


@tool()
@safe_tool
def record_payout(params: RecordPayoutIn) -> dict[str, Any]:
    """Confirm a completed Greenlight transfer (parent-only, same-family).

    This records bookkeeping only; it does not send money. Supply the actual
    transfer date and a stable idempotency key, reusing that key and identical
    details when retrying. Only approved earnings may be paid. Description is
    the transfer memo; an optional timecard must be approved and paid in full.
    """
    parent = require_parent()
    child = resolve_child_in_family(parent, params.user_id)

    payload = params.model_dump()
    payload["memo"] = payload.pop("description")
    serializer = GreenlightPayoutSerializer(data=payload)
    try:
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("user_id")
        transfer, _ = confirm_transfer(child, parent, **data)
    except APIException as exc:
        raise MCPValidationError(str(exc.detail)) from exc
    return payment_entry_to_dict(transfer.payment_entry)


@tool()
@safe_tool
def adjust_payment(params: AdjustPaymentIn) -> dict[str, Any]:
    """Apply a positive or negative manual adjustment to a child's balance.

    Supply a stable request_id UUID. Identical retries return the saved
    entry without applying the adjustment again; changed inputs conflict.
    """
    parent = require_parent()
    child = resolve_child_in_family(parent, params.user_id)

    return mutation_once(
        actor=parent, target=child, operation="adjust_payment", request_id=params.request_id,
        payload=params.model_dump(exclude={"request_id"}), result_model=PaymentLedger,
        create=lambda actor, target: PaymentService.record_entry(
            target, params.amount, PaymentLedger.EntryType.ADJUSTMENT,
            description=params.description, created_by=actor,
        ),
        serialize=payment_entry_to_dict,
    )
