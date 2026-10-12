"""Positive acquisition policy for the recorded prepared companion art.

Saved inventory/collections are not deleted or rewritten by this policy.
Domain services still own compatibility, permissions, rewards and transactions.
Tests may supply an explicit scoped RPG_ASSET_SUPPORT_POLICY dictionary to
exercise synthetic catalog behavior without weakening the production registry.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


POLICY_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/asset-support.json"


@dataclass(frozen=True)
class PetArtRule:
    species_slug: str
    sprite_key: str
    potion_slugs: frozenset[str]


@dataclass(frozen=True)
class CatalogPolicy:
    pets: tuple[PetArtRule, ...]
    potion_slugs: frozenset[str]
    disabled_item_types: frozenset[str]


def _strings(value, field):
    if not isinstance(value, (list, tuple)) or any(not isinstance(entry, str) or not entry for entry in value):
        raise ImproperlyConfigured(f"Asset support {field} must be a list of nonempty strings")
    return frozenset(value)


def _parse_policy(value):
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        raise ImproperlyConfigured("Asset support policy requires schema_version 1")
    potions = _strings(value.get("potion_slugs"), "potion_slugs")
    entries = value.get("pets")
    if not isinstance(entries, (list, tuple)):
        raise ImproperlyConfigured("Asset support pets must be a list")
    pets, identities = [], set()
    for entry in entries:
        if not isinstance(entry, Mapping) or any(not isinstance(entry.get(key), str) or not entry[key] for key in ("species_slug", "sprite_key")):
            raise ImproperlyConfigured("Asset support pets need exact species_slug and sprite_key")
        supported = _strings(entry.get("potion_slugs"), "pet potion_slugs")
        identity = (entry["species_slug"], entry["sprite_key"])
        if not supported or not supported.issubset(potions) or identity in identities:
            raise ImproperlyConfigured("Asset support pet variants must be unique and use approved potions")
        identities.add(identity)
        pets.append(PetArtRule(*identity, supported))
    return CatalogPolicy(
        tuple(pets), potions,
        _strings(value.get("disabled_item_types", ["cosmetic_pet_accessory"]), "disabled_item_types"),
    )


@lru_cache(maxsize=1)
def _default_policy():
    return _parse_policy(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


def _policy():
    override = getattr(settings, "RPG_ASSET_SUPPORT_POLICY", None)
    return _default_policy() if override is None else _parse_policy(override)


def _value(entity, field, default=None):
    return entity.get(field, default) if isinstance(entity, Mapping) else getattr(entity, field, default)


def _pet_rule(species, policy):
    slug, sprite = _value(species, "slug"), _value(species, "sprite_key")
    return next((entry for entry in policy.pets if entry.species_slug == slug and entry.sprite_key == sprite), None)


def pet_is_available(species, potion=None):
    """Check art identity only; domain compatibility is enforced separately."""
    rule = _pet_rule(species, _policy())
    if rule is None:
        return False
    return potion is None or _value(potion, "slug") in rule.potion_slugs


species_is_available = pet_is_available


def potion_is_available(potion):
    return _value(potion, "slug") in _policy().potion_slugs


def available_pet_variants(species):
    """Return approved potion rows within the existing authored compatibility."""
    from apps.pets.models import PotionType

    rule = _pet_rule(species, _policy())
    if rule is None:
        return PotionType.objects.none()
    variants = PotionType.objects.filter(slug__in=rule.potion_slugs)
    authored = species.available_potions
    if authored.exists():
        variants = variants.filter(pk__in=authored.values("pk"))
    return variants


def _legacy_reference(model, value):
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip()
    # Existing hatch services resolve legacy names case-insensitively. Keep
    # that precedence, then support canonical slugs without trusting artwork
    # names or granting an absent catalog identity.
    return model.objects.filter(name__iexact=key).first() or model.objects.filter(slug=key).first()


def item_is_available(item):
    from apps.pets.models import PetSpecies, PotionType

    kind = _value(item, "item_type")
    if kind in _policy().disabled_item_types:
        return False
    metadata = _value(item, "metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    if kind == "egg":
        species = _value(item, "pet_species")
        if species is None:
            species = _legacy_reference(PetSpecies, metadata.get("species"))
        return pet_is_available(species)
    if kind == "potion":
        potion = _value(item, "potion_type")
        if potion is None:
            potion = _legacy_reference(PotionType, metadata.get("variant"))
        return potion_is_available(potion)
    # DOM frames/titles/covers, food, coins and utility items need no fitted
    # creature art. Their existing service still validates actual metadata.
    return item is not None


def available_items(queryset):
    """Filter a queryset/iterable without changing its existing order."""
    return [item for item in queryset if item_is_available(item)]


def item_unavailable_reason(item):
    if item_is_available(item):
        return None
    if _value(item, "item_type") == "cosmetic_pet_accessory":
        return "Pet accessories are not available for the current companion artwork."
    return "This item needs companion artwork that is not currently supported."
