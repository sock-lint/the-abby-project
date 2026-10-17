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


def prepared_base_potion(item):
    """New families reuse the existing canonical global Base ingredient."""
    metadata = getattr(item, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    return (
        getattr(item, "item_type", None) == "potion" and getattr(item, "slug", None) == "base-potion"
        and getattr(item, "potion_type_id", None) is not None and item.potion_type.slug == "base"
        and metadata.get("variant") == "base"
    )
