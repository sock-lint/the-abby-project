"""Money ↔ Coins exchange MCP tools.

Mirrors ``/api/coins/exchange/*``. The rate (``COINS_PER_DOLLAR``, default 10)
is snapshotted on the request — money is NOT held at request time, so
``approve`` can raise ``InsufficientFundsError`` if the balance has dropped
since the request was filed. Reject has no ledger side-effects.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings

from apps.rewards.models import ExchangeRequest
from apps.rewards.services import ExchangeService

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    DecideExchangeIn,
    GetExchangeRateIn,
    ListExchangeRequestsIn,
    RequestExchangeIn,
)
from ..server import tool
from ..shapes import exchange_request_to_dict, many


@tool()
@safe_tool
def get_exchange_rate(params: GetExchangeRateIn) -> dict[str, Any]:
    """Return the current ``COINS_PER_DOLLAR`` rate."""
    get_current_user()
    return {"coins_per_dollar": int(django_settings.COINS_PER_DOLLAR)}


@tool()
@safe_tool
def list_exchange_requests(params: ListExchangeRequestsIn) -> dict[str, Any]:
    """List exchange requests. Children see their own; parents see any child."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = ExchangeRequest.objects.filter(user=target)
    if params.status:
        qs = qs.filter(status=params.status)
    qs = qs.order_by("-created_at")[: params.limit]
    return {"exchanges": many(qs, exchange_request_to_dict)}


@tool()
@safe_tool
def request_exchange(params: RequestExchangeIn) -> dict[str, Any]:
    """Request a money → coins exchange (child self-scoped).

    Validates a $1.00 minimum and current balance, snapshots the rate,
    and notifies parents. The dollar amount is NOT held — parents can
    approve any time, but approval re-checks the balance.
    """
    user = get_current_user()
    if user.role == "parent":
        raise MCPPermissionDenied(
            "Exchanges are filed by the child. Use approve_exchange / reject_exchange "
            "to act on a child's request."
        )
    exchange = ExchangeService.request_exchange(user, params.dollar_amount)
    return exchange_request_to_dict(exchange)


@tool()
@safe_tool
def approve_exchange(params: DecideExchangeIn) -> dict[str, Any]:
    """Approve a pending exchange (parent-only).

    Re-checks the child's payment balance; raises
    ``InsufficientFundsError`` (surfaced as MCPValidationError) if the
    balance has dropped below the requested dollar amount since filing.
    """
    parent = require_parent()
    try:
        exchange = ExchangeRequest.objects.select_related("user").get(
            pk=params.exchange_id,
        )
    except ExchangeRequest.DoesNotExist:
        raise MCPNotFoundError(f"ExchangeRequest {params.exchange_id} not found.")
    updated = ExchangeService.approve(exchange, parent, notes=params.notes)
    return exchange_request_to_dict(updated)


@tool()
@safe_tool
def reject_exchange(params: DecideExchangeIn) -> dict[str, Any]:
    """Deny a pending exchange (parent-only). No ledger side-effects."""
    parent = require_parent()
    try:
        exchange = ExchangeRequest.objects.select_related("user").get(
            pk=params.exchange_id,
        )
    except ExchangeRequest.DoesNotExist:
        raise MCPNotFoundError(f"ExchangeRequest {params.exchange_id} not found.")
    updated = ExchangeService.reject(exchange, parent, notes=params.notes)
    return exchange_request_to_dict(updated)
