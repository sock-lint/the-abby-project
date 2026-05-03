"""Rewards-related MCP tools (Coins, Rewards, Redemptions)."""
from __future__ import annotations

from typing import Any

from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService

from ..context import (
    get_current_user, get_in_family, require_parent,
    resolve_child_in_family, resolve_target_user,
)
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    AdjustCoinsIn,
    CreateRewardIn,
    DecideRedemptionIn,
    DeleteRewardIn,
    GetCoinBalanceIn,
    ListRewardsIn,
    RequestRedemptionIn,
    UpdateRewardIn,
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
    """List rewards in the shop along with the current user's coin balance.

    Audit C8: ``Reward`` is per-family content (``Reward.family`` FK).
    Without scoping, this returned every household's shop to every user.
    """
    user = get_current_user()
    family_id = getattr(user, "family_id", None)
    if family_id is None:
        return {
            "rewards": [],
            "balance": CoinService.get_balance(user),
        }
    qs = Reward.objects.filter(family_id=family_id)
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
    # Audit C8: Reward is per-family content. Without family-scoping a child
    # could redeem rewards from any other family's shop — spending their
    # own coins, decrementing the foreign family's stock, and creating a
    # pending redemption row that the foreign parents would see.
    reward = get_in_family(
        Reward, params.reward_id, actor=user, family_path="family",
    )

    redemption = RewardService.request_redemption(user, reward)
    return redemption_to_dict(redemption)


def _get_pending_redemption(redemption_id: int, parent) -> RewardRedemption:
    """Fetch a pending redemption family-scoped to the calling parent.

    Audit C8 + H13: previously bare ``get(pk=...)`` with no status filter
    or family scope. A parent could approve another family's pending
    redemption (crediting the foreign child with the digital item) or
    probe arbitrary redemption ids by 404-vs-success distinction.
    """
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Redemption {redemption_id} not found.")
    try:
        return RewardRedemption.objects.select_related("user", "reward").get(
            pk=redemption_id,
            user__family_id=family_id,
        )
    except RewardRedemption.DoesNotExist:
        raise MCPNotFoundError(f"Redemption {redemption_id} not found.")


@tool()
@safe_tool
def approve_redemption(params: DecideRedemptionIn) -> dict[str, Any]:
    """Approve a pending redemption (parent-only)."""
    parent = require_parent()
    redemption = _get_pending_redemption(params.redemption_id, parent)
    updated = RewardService.approve(redemption, parent, notes=params.notes)
    return redemption_to_dict(updated)


@tool()
@safe_tool
def reject_redemption(params: DecideRedemptionIn) -> dict[str, Any]:
    """Reject a pending redemption and refund the held coins (parent-only)."""
    parent = require_parent()
    redemption = _get_pending_redemption(params.redemption_id, parent)
    updated = RewardService.reject(redemption, parent, notes=params.notes)
    return redemption_to_dict(updated)


# ---------------------------------------------------------------------------
# Tier 1.3: Reward shop CRUD + coin adjustments
# ---------------------------------------------------------------------------


def _resolve_item_definition(slug: str | None):
    """Look up an ItemDefinition by slug, raising if slug is set but missing."""
    if not slug:
        return None
    from apps.rpg.models import ItemDefinition
    try:
        return ItemDefinition.objects.get(slug=slug)
    except ItemDefinition.DoesNotExist:
        raise MCPValidationError(
            f"item_definition_slug {slug!r} does not match any ItemDefinition.",
        )


@tool()
@safe_tool
def create_reward(params: CreateRewardIn) -> dict[str, Any]:
    """Create a new shop reward (parent-only). Images are not supported via MCP.

    Pair ``fulfillment_kind='digital_item'`` (or ``'both'``) with
    ``item_definition_slug`` to link the reward to an RPG inventory item —
    approval will credit it to the user's UserInventory automatically.

    The ``image`` field is parent-UI-only (MCP can't upload files). Leave
    unset here and attach art via /manage when needed.
    """
    parent = require_parent()
    item_def = _resolve_item_definition(params.item_definition_slug)
    if params.fulfillment_kind != "real_world" and item_def is None:
        raise MCPValidationError(
            "fulfillment_kind requires item_definition_slug for non-real_world "
            "rewards.",
        )
    family = getattr(parent, "family", None)
    if family is None:
        raise MCPValidationError("Calling parent has no family attached.")
    # Audit C8: name uniqueness is per-family — Reward is per-family content.
    if Reward.objects.filter(name=params.name, family=family).exists():
        raise MCPValidationError(f"A reward named {params.name!r} already exists.")
    reward = Reward.objects.create(
        name=params.name,
        description=params.description,
        icon=params.icon,
        cost_coins=params.cost_coins,
        rarity=params.rarity,
        stock=params.stock,
        requires_parent_approval=params.requires_parent_approval,
        is_active=params.is_active,
        order=params.order,
        fulfillment_kind=params.fulfillment_kind,
        item_definition=item_def,
        family=family,
    )
    return reward_to_dict(reward)


@tool()
@safe_tool
def update_reward(params: UpdateRewardIn) -> dict[str, Any]:
    """Edit an existing reward (parent-only).

    Pass ``clear_stock=True`` to set stock to None (unlimited). Pass
    ``clear_item_definition=True`` to unlink from an RPG item. Otherwise
    only the fields you set are updated.
    """
    parent = require_parent()
    # Audit C8: per-family content; scope by Reward.family.
    reward = get_in_family(
        Reward, params.reward_id, actor=parent, family_path="family",
    )

    data = params.model_dump(
        exclude={
            "reward_id", "clear_stock", "item_definition_slug",
            "clear_item_definition",
        },
        exclude_unset=True,
    )
    # Audit C8: name uniqueness is per-family.
    if "name" in data and Reward.objects.filter(
        name=data["name"], family_id=reward.family_id,
    ).exclude(pk=reward.pk).exists():
        raise MCPValidationError(
            f"Another reward is already named {data['name']!r}.",
        )
    for field, value in data.items():
        setattr(reward, field, value)
    if params.clear_stock:
        reward.stock = None
    if params.clear_item_definition:
        reward.item_definition = None
    elif params.item_definition_slug is not None:
        reward.item_definition = _resolve_item_definition(
            params.item_definition_slug,
        )
    reward.save()
    return reward_to_dict(reward)


@tool()
@safe_tool
def delete_reward(params: DeleteRewardIn) -> dict[str, Any]:
    """Delete a reward from the shop (parent-only).

    Refuses if there are any RewardRedemption rows still linked — the
    ForeignKey on redemption is ``on_delete=PROTECT`` so historical
    receipts keep their reward reference. Deactivate via ``update_reward
    is_active=False`` instead.
    """
    parent = require_parent()
    # Audit C8: per-family content; scope by Reward.family.
    reward = get_in_family(
        Reward, params.reward_id, actor=parent, family_path="family",
    )
    if reward.redemptions.exists():
        raise MCPValidationError(
            f"Reward {params.reward_id} has redemption history and cannot be "
            "deleted. Set is_active=False to hide it from the shop instead.",
        )
    reward_id = reward.pk
    reward.delete()
    return {"reward_id": reward_id, "deleted": True}


@tool()
@safe_tool
def adjust_coins(params: AdjustCoinsIn) -> dict[str, Any]:
    """Grant or revoke coins for a child (parent-only, same-family).

    Mirrors the ``POST /api/coins/adjust/`` endpoint. Positive amounts
    grant coins; negative amounts revoke — the service re-validates the
    balance before posting a negative entry to prevent going below zero.
    Audit C3: ``resolve_child_in_family`` enforces that ``user_id`` is a
    child in the caller's own family.
    """
    parent = require_parent()
    target = resolve_child_in_family(parent, params.user_id)
    if params.amount == 0:
        raise MCPValidationError("amount must not be 0.")
    if params.amount > 0:
        entry = CoinService.award_coins(
            target,
            params.amount,
            CoinLedger.Reason.ADJUSTMENT,
            description=params.description,
            created_by=parent,
        )
    else:
        entry = CoinService.spend_coins(
            target,
            abs(params.amount),
            CoinLedger.Reason.ADJUSTMENT,
            description=params.description,
        )
    new_balance = CoinService.get_balance(target)
    return {
        "user_id": target.id,
        "entry_id": entry.id if entry else None,
        "amount": params.amount,
        "new_balance": int(new_balance),
    }
