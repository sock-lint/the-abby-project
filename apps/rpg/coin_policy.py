"""Versioned values for newly drawn Coin pouches, never established rewards.

Original definitions remain the weighted candidates and the identity of owned,
authored and frozen rewards. Substitute only after a new random draw, before
granting inventory or freezing expedition loot. Replacement definitions are
excluded from raw random pools to keep the original odds and candidate count.
"""
from collections.abc import Mapping


RANDOM_POUCH_VALUES = {
    "pouch-small": (5, 1),
    "pouch-rupee": (10, 2),
    "pouch-medium": (15, 3),
    "pouch-large": (50, 10),
    "pouch-gold": (100, 20),
    "pouch-treasure": (250, 50),
    "pouch-mega": (500, 100),
}
RANDOM_POUCH_REPLACEMENTS = {slug: f"{slug}-v2" for slug in RANDOM_POUCH_VALUES}


def resolve_random_pouch(item, *, items_by_slug=None):
    """Resolve one new draw, optionally against an already detached catalog.

    This never creates or edits catalog rows. Missing or altered replacement
    definitions fail the enclosing award transaction instead of granting the
    original expensive pouch. Synthetic and separately authored identities
    outside the fixed mapping keep their existing rules.
    """
    slug = getattr(item, "slug", None)
    target_slug = RANDOM_POUCH_REPLACEMENTS.get(slug)
    if target_slug is None or item.item_type != "coin_pouch":
        return item
    if items_by_slug is None:
        from .models import ItemDefinition
        target = ItemDefinition.objects.filter(slug=target_slug).first()
    else:
        target = items_by_slug.get(target_slug)
    expected = RANDOM_POUCH_VALUES[slug][1]
    metadata = getattr(target, "metadata", None)
    if (
        target is None or target.item_type != "coin_pouch" or target.rarity != item.rarity
        or target.coin_value != expected or not isinstance(metadata, Mapping)
        or type(metadata.get("coins")) is not int or metadata["coins"] != expected
        or metadata.get("no_random_drop") is not True
    ):
        raise ValueError("The new random Coin pouch definition is unavailable.")
    return target
