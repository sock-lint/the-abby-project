"""RPG inventory & cosmetics MCP tools.

Wraps ConsumableService + CosmeticService. Cosmetics opt-in via the four
slot fields on ``CharacterProfile``: ``active_frame`` / ``active_title``
/ ``active_theme`` / ``active_pet_accessory``. Trophy badge is a separate
``active_trophy_badge`` FK that the user must have actually earned (via
``UserBadge``) — enforced here, not at the schema level.
"""
from __future__ import annotations

from typing import Any

from apps.achievements.models import Badge, UserBadge
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, CosmeticService

from ..context import get_current_user, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..schemas import (
    EquipCosmeticIn,
    ListCosmeticsIn,
    ListInventoryIn,
    SetTrophyBadgeIn,
    UnequipCosmeticIn,
    UseConsumableIn,
)
from ..server import tool
from ..shapes import inventory_entry_to_dict, item_definition_to_dict, many


@tool()
@safe_tool
def list_inventory(params: ListInventoryIn) -> dict[str, Any]:
    """List a user's inventory entries (children forced to self).

    Optionally filter by ``item_type`` slug. Returns nested ItemDefinition
    metadata so a caller can render rarity / icon / sprite_key without a
    second round-trip.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = UserInventory.objects.select_related("item").filter(user=target)
    if params.item_type:
        qs = qs.filter(item__item_type=params.item_type)
    qs = qs.order_by("item__item_type", "item__rarity", "item__name")
    return {"inventory": many(qs, inventory_entry_to_dict)}


@tool()
@safe_tool
def use_consumable(params: UseConsumableIn) -> dict[str, Any]:
    """Use one of a CONSUMABLE-type item.

    Each consumable maps to an effect via ``metadata.effect`` — see the
    "Consumables" gotcha in CLAUDE.md for the 14 supported slugs. Decrements
    the inventory quantity by 1. Returns the service's effect detail dict.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    return ConsumableService.use(target, params.item_id)


@tool()
@safe_tool
def list_cosmetics(params: ListCosmeticsIn) -> dict[str, Any]:
    """Return owned cosmetics grouped by slot, plus current equipped state."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    owned = CosmeticService.list_owned_cosmetics(target)
    profile, _ = CharacterProfile.objects.get_or_create(user=target)

    grouped = {
        slot: [item_definition_to_dict(item) for item in items]
        for slot, items in owned.items()
    }
    equipped = {
        "active_frame": (
            item_definition_to_dict(profile.active_frame) if profile.active_frame else None
        ),
        "active_title": (
            item_definition_to_dict(profile.active_title) if profile.active_title else None
        ),
        "active_theme": (
            item_definition_to_dict(profile.active_theme) if profile.active_theme else None
        ),
        "active_pet_accessory": (
            item_definition_to_dict(profile.active_pet_accessory)
            if profile.active_pet_accessory else None
        ),
    }
    trophy = profile.active_trophy_badge
    return {
        "owned": grouped,
        "equipped": equipped,
        "active_trophy_badge_id": trophy.id if trophy else None,
    }


@tool()
@safe_tool
def equip_cosmetic(params: EquipCosmeticIn) -> dict[str, Any]:
    """Equip a cosmetic to its slot. Caller must own one in inventory."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    return CosmeticService.equip(target, params.item_id)


@tool()
@safe_tool
def unequip_cosmetic(params: UnequipCosmeticIn) -> dict[str, Any]:
    """Clear a cosmetic slot."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    return CosmeticService.unequip(target, params.slot)


@tool()
@safe_tool
def set_trophy_badge(params: SetTrophyBadgeIn) -> dict[str, Any]:
    """Set or clear the user's hero ``active_trophy_badge``.

    Pass ``badge_id=None`` to clear. The caller must have *earned* the
    badge (a row in ``UserBadge``) — the trophy slot enforces ownership
    here even though the FK schema is loose.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    profile, _ = CharacterProfile.objects.get_or_create(user=target)

    if params.badge_id is None:
        profile.active_trophy_badge = None
        profile.save(update_fields=["active_trophy_badge", "updated_at"])
        return {"active_trophy_badge_id": None}

    try:
        badge = Badge.objects.get(pk=params.badge_id)
    except Badge.DoesNotExist:
        raise MCPNotFoundError(f"Badge {params.badge_id} not found.")
    if not UserBadge.objects.filter(user=target, badge=badge).exists():
        raise MCPPermissionDenied(
            "You can only choose a trophy from badges you've earned.",
        )
    profile.active_trophy_badge = badge
    profile.save(update_fields=["active_trophy_badge", "updated_at"])
    return {
        "active_trophy_badge_id": badge.id,
        "name": badge.name,
        "rarity": badge.rarity,
    }
