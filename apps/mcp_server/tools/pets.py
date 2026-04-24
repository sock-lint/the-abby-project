"""Pets / Mounts / Breeding MCP tools.

Wraps PetService — hatch, feed, evolve (auto on growth >= 100), set
active, and breed. Mirrors the REST endpoints under ``/api/pets/`` and
``/api/mounts/``.

Gotchas (see CLAUDE.md "Pets & mounts" section):
- (user, species, potion) is unique — can't hatch a duplicate combo.
- Only one active pet AND one active mount per user; activate
  deactivates the prior in the same transaction.
- Breeding: 7-day per-mount cooldown, 2% chromatic upgrade chance,
  same-mount pair raises ValueError.
"""
from __future__ import annotations

from typing import Any

from apps.pets.models import UserMount, UserPet
from apps.pets.services import PetService

from ..context import get_current_user, resolve_target_user
from ..errors import safe_tool
from ..schemas import (
    ActivateMountIn,
    ActivatePetIn,
    BreedMountsIn,
    FeedPetIn,
    GetPetStableIn,
    HatchPetIn,
    ListMountsIn,
    ListPetsIn,
)
from ..server import tool
from ..shapes import many, user_mount_to_dict, user_pet_to_dict


@tool()
@safe_tool
def list_pets(params: ListPetsIn) -> dict[str, Any]:
    """List a user's pets (children forced to self)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = UserPet.objects.select_related("species", "potion").filter(user=target)
    return {"pets": many(qs, user_pet_to_dict)}


@tool()
@safe_tool
def list_mounts(params: ListMountsIn) -> dict[str, Any]:
    """List a user's evolved mounts."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = UserMount.objects.select_related("species", "potion").filter(user=target)
    return {"mounts": many(qs, user_mount_to_dict)}


@tool()
@safe_tool
def get_pet_stable(params: GetPetStableIn) -> dict[str, Any]:
    """Aggregate stable view: pets + mounts + collection stats."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    raw = PetService.get_stable(target)
    return {
        "pets": many(raw["pets"], user_pet_to_dict),
        "mounts": many(raw["mounts"], user_mount_to_dict),
        "total_pets": raw["total_pets"],
        "total_mounts": raw["total_mounts"],
        "total_possible": raw["total_possible"],
    }


@tool()
@safe_tool
def hatch_pet(params: HatchPetIn) -> dict[str, Any]:
    """Hatch an egg + potion into a new pet (consumes both items)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    pet = PetService.hatch_pet(target, params.egg_item_id, params.potion_item_id)
    return user_pet_to_dict(pet)


@tool()
@safe_tool
def feed_pet(params: FeedPetIn) -> dict[str, Any]:
    """Feed a food item to a pet. Auto-evolves at growth >= 100.

    Returns ``{growth_added, new_growth, evolved, mount_id}`` plus the
    refreshed pet shape so the caller can read the new growth bar in
    one call.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    result = PetService.feed_pet(target, params.pet_id, params.food_item_id)
    pet = UserPet.objects.select_related("species", "potion").get(pk=params.pet_id)
    return {**result, "pet": user_pet_to_dict(pet)}


@tool()
@safe_tool
def activate_pet(params: ActivatePetIn) -> dict[str, Any]:
    """Mark a pet as active (deactivates any prior active pet)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    pet = PetService.set_active_pet(target, params.pet_id)
    return user_pet_to_dict(pet)


@tool()
@safe_tool
def activate_mount(params: ActivateMountIn) -> dict[str, Any]:
    """Mark a mount as active (deactivates any prior active mount)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    mount = PetService.set_active_mount(target, params.mount_id)
    return user_mount_to_dict(mount)


@tool()
@safe_tool
def breed_mounts(params: BreedMountsIn) -> dict[str, Any]:
    """Combine two mounts to yield a hybrid egg + potion pair.

    Per-mount 7-day cooldown; 1-in-50 chance to override the picked
    potion with Cosmic (legendary). Same-mount pairs raise an error.
    Returns the roll summary with cooldown info.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    return PetService.breed_mounts(target, params.mount_a_id, params.mount_b_id)
