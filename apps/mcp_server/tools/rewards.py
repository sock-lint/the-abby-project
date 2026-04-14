"""Rewards-related MCP tools (Coins, Rewards, Redemptions)."""
from __future__ import annotations

from typing import Any

from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, safe_tool
from ..schemas import (
    DecideRedemptionIn,
    GetCoinBalanceIn,
    ListRewardsIn,
    RequestRedemptionIn,
)
from ..server import tool
from ..shapes import (
    coin_ledger_entry_to_dict,
    redemption_to_dict,
    reward_to_dict,
    to_plain,
)


@tool()
@safe_tool
def list_rewards(params: ListRewardsIn) -> dict[str, Any]:
    """List rewards in the shop along with the current user's coin balance."""
    user = get_current_user()
    qs = Reward.objects.all()
    if params.active_only:
        qs = qs.filter(is_active=True)
    rewards = list(qs.order_by("order", "cost_coins", "name"))
    return {
        "rewards": [reward_to_dict(r) for r in rewards],
        "balance": CoinService.get_balance(user),
    }


@tool()
@safe_tool
def get_coin_balance(params: GetCoinBalanceIn) -> dict[str, Any]:
    """Return coin balance, per-reason breakdown, and recent ledger entries."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

    balance = CoinService.get_balance(target)
    breakdown = CoinService.get_breakdown(target)
    recent = list(
        CoinLedger.objects.filter(user=target).order_by("-created_at")[:25]
    )
    return {
        "balance": int(balance),
        "breakdown": to_plain(breakdown),
        "recent_ledger": [coin_ledger_entry_to_dict(e) for e in recent],
    }


@tool()
@safe_tool
def request_redemption(params: RequestRedemptionIn) -> dict[str, Any]:
    """Request a reward redemption on behalf of the current user.

    Deducts coins immediately (held) and — depending on the reward —
    either fulfills immediately or creates a PENDING request for parent
    approval. Delegates to :class:`RewardService.request_redemption`.
    """
    user = get_current_user()
    try:
        reward = Reward.objects.get(pk=params.reward_id)
    except Reward.DoesNotExist:
        raise MCPNotFoundError(f"Reward {params.reward_id} not found.")

    redemption = RewardService.request_redemption(user, reward)
    return redemption_to_dict(redemption)


def _get_pending_redemption(redemption_id: int) -> RewardRedemption:
    try:
        return RewardRedemption.objects.select_related("user", "reward").get(
            pk=redemption_id,
        )
    except RewardRedemption.DoesNotExist:
        raise MCPNotFoundError(f"Redemption {redemption_id} not found.")


@tool()
@safe_tool
def approve_redemption(params: DecideRedemptionIn) -> dict[str, Any]:
    """Approve a pending redemption (parent-only)."""
    parent = require_parent()
    redemption = _get_pending_redemption(params.redemption_id)
    updated = RewardService.approve(redemption, parent, notes=params.notes)
    return redemption_to_dict(updated)


@tool()
@safe_tool
def reject_redemption(params: DecideRedemptionIn) -> dict[str, Any]:
    """Reject a pending redemption and refund the held coins (parent-only)."""
    parent = require_parent()
    redemption = _get_pending_redemption(params.redemption_id)
    updated = RewardService.reject(redemption, parent, notes=params.notes)
    return redemption_to_dict(updated)
