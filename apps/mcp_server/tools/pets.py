"""Pets / Mounts MCP tools.

Wraps PetService — incubate, explicitly hatch when ready, feed, evolve (auto on growth >= 100), set
active. Mirrors the REST endpoints under ``/api/pets/`` and
``/api/mounts/``.

Gotchas (see CLAUDE.md "Pets & mounts" section):
- (user, species, potion) is unique — can't hatch a duplicate combo.
- Only one active pet AND one active mount per user; activate
  deactivates the prior in the same transaction.
"""
from __future__ import annotations

from typing import Any

from apps.pets.models import UserMount, UserPet
from django.utils import timezone
from rest_framework import serializers

from apps.pets.services import IncubationNotFound, PetService
from apps.pets.serializers import PetIncubationSerializer

from ..context import get_current_user, resolve_target_user
from ..errors import MCPNotFoundError, safe_tool
from ..schemas import (
    ActivateMountIn,
    ActivatePetIn,
    FeedPetIn,
    GetPetStableIn,
    GetPetIncubationIn,
    StartPetIncubationIn,
    ClaimPetIncubationIn,
    ListMountsIn,
    ListPetsIn,
)
from ..retries import authorized_household
from ..server import tool
from ..shapes import many, user_mount_to_dict, user_pet_to_dict


@tool()
@safe_tool
def list_pets(params: ListPetsIn) -> dict[str, Any]:
    """List a user's pets (children forced to self)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target, allow_inactive_target=True) as (user, target):
        qs = UserPet.objects.select_related("species", "potion").filter(user=target)
        return {"pets": many(qs, user_pet_to_dict)}


@tool()
@safe_tool
def list_mounts(params: ListMountsIn) -> dict[str, Any]:
    """List a user's evolved mounts."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target, allow_inactive_target=True) as (user, target):
        qs = UserMount.objects.select_related("species", "potion").filter(user=target)
        return {"mounts": many(qs, user_mount_to_dict)}


@tool()
@safe_tool
def get_pet_stable(params: GetPetStableIn) -> dict[str, Any]:
    """Aggregate stable view: pets + mounts + collection stats."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target, allow_inactive_target=True) as (user, target):
        raw = PetService.get_stable(target)
        return {
            "pets": many(raw["pets"], user_pet_to_dict),
            "mounts": many(raw["mounts"], user_mount_to_dict),
            "total_pets": raw["total_pets"],
            "total_mounts": raw["total_mounts"],
            "total_possible": raw["total_possible"],
        }


def _incubation_body(incubation, now):
    return {
        "incubation": PetIncubationSerializer(incubation, context={"as_of": now}).data if incubation else None,
        "server_now": serializers.DateTimeField().to_representation(now),
    }


@tool()
@safe_tool
def get_pet_incubation(params: GetPetIncubationIn) -> dict[str, Any]:
    """Read the current incubating or ready egg. Reads never hatch a pet."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target, allow_inactive_target=True) as (user, target):
        now = timezone.now()
        return {**_incubation_body(PetService.current_incubation(target), now),
                "duration_seconds": PetService.incubation_duration_seconds()}


@tool()
@safe_tool
def start_pet_incubation(params: StartPetIncubationIn) -> dict[str, Any]:
    """Consume one egg and potion to begin incubation, without creating a pet.

    Retry identical ingredients with the same request_id after an uncertain
    result. Only one unhatched incubation can be active for the account.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target) as (user, target):
        incubation, _ = PetService.start_incubation(target, params.egg_item_id, params.potion_item_id, params.request_id)
        return _incubation_body(incubation, timezone.now())


@tool()
@safe_tool
def claim_pet_incubation(params: ClaimPetIncubationIn) -> dict[str, Any]:
    """Explicitly hatch a ready incubation. Early calls grant nothing.

    Exact-ID retries return the same saved pet without another reward.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target) as (user, target):
        try:
            incubation, pet, freshly_hatched = PetService.hatch_incubation(target, params.incubation_id)
        except IncubationNotFound as exc:
            raise MCPNotFoundError(str(exc)) from exc
        return {**_incubation_body(incubation, timezone.now()),
                "pet": user_pet_to_dict(pet), "freshly_hatched": freshly_hatched}


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
    with authorized_household(user, target) as (user, target):
        result = PetService.feed_pet(target, params.pet_id, params.food_item_id)
        pet = UserPet.objects.select_related("species", "potion").get(pk=params.pet_id, user=target)
        return {**result, "pet": user_pet_to_dict(pet)}


@tool()
@safe_tool
def activate_pet(params: ActivatePetIn) -> dict[str, Any]:
    """Mark a pet as active (deactivates any prior active pet)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target) as (user, target):
        pet = PetService.set_active_pet(target, params.pet_id)
        return user_pet_to_dict(pet)


@tool()
@safe_tool
def activate_mount(params: ActivateMountIn) -> dict[str, Any]:
    """Mark a mount as active (deactivates any prior active mount)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with authorized_household(user, target) as (user, target):
        mount = PetService.set_active_mount(target, params.mount_id)
        return user_mount_to_dict(mount)
