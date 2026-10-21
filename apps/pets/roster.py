"""Exact public receiving identities for the prepared companion roster."""
import json
from pathlib import Path
from collections.abc import Mapping


ROSTER_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/companion-roster.json"
ROSTER = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
FAMILIES = {family["species_slug"]: family for family in ROSTER["families"]}
RETIRED_SPECIES_SLUGS = frozenset(ROSTER["retired_species_slugs"])


def prepared_family(species):
    """A matching word or sprite filename never establishes a new identity."""
    if species is None:
        return None
    slug = species.get("slug") if isinstance(species, Mapping) else getattr(species, "slug", None)
    sprite = species.get("sprite_key") if isinstance(species, Mapping) else getattr(species, "sprite_key", None)
    family = FAMILIES.get(slug)
    return family if family and sprite == family["sprite_key"] else None


def prepared_potion(item):
    """Recognize a canonical global ingredient independently of art approval.

    Exact positive artwork policy and species compatibility still determine
    whether a recognized ingredient may start a new incubation.
    """
    value = item.get if isinstance(item, Mapping) else lambda key, default=None: getattr(item, key, default)
    metadata = value("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    potion = value("potion_type")
    slug = potion.get("slug") if isinstance(potion, Mapping) else getattr(potion, "slug", None)
    return (
        value("item_type") == "potion" and slug in {"base", "fire", "ice"}
        and value("potion_type_id") is not None and value("slug") == f"{slug}-potion"
        and metadata.get("variant") == slug
    )


def prepared_base_potion(item):
    """Retain the canonical Base-only predicate for existing callers."""
    slug = item.get("slug") if isinstance(item, Mapping) else getattr(item, "slug", None)
    return slug == "base-potion" and prepared_potion(item)
