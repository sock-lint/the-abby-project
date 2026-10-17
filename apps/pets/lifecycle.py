"""Shared lifecycle vocabulary, independent of creature artwork and rewards.

An egg is an inventory item. A hatched pet keeps its existing identity as
it grows; only confirmed evolution (or an existing mount) selects Grown.
These read-only projections never create ownership or change growth.
"""
import json
from pathlib import Path


LIFECYCLE_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/companion-lifecycle.json"
_DEFINITION = json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8"))
LIFECYCLE_STAGES = tuple(stage["id"] for stage in _DEFINITION["stages"])
MIDDLE_GROWTH = _DEFINITION["middle_growth"]
GROWN_GROWTH = _DEFINITION["grown_growth"]


def companion_lifecycle_stage(companion, *, is_mount=False):
    """Derive a stage from saved state, including legacy/unsupported families."""
    if is_mount or getattr(companion, "evolved_to_mount", False):
        return "grown"
    return "middle" if companion.growth_points >= MIDDLE_GROWTH else "baby"


def item_lifecycle_stage(item):
    return "egg" if item.item_type == "egg" else None


def egg_species_slug(item):
    """Keep egg family identity separate from any current presentation key.

    Typed references take precedence over old metadata. Legacy catalog rows
    may store a display name or canonical slug, as in the acquisition policy.
    Unknown eggs remain readable without inventing a species identity.
    """
    if item.item_type != "egg":
        return None
    if item.pet_species_id:
        return item.pet_species.slug
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    key = metadata.get("species")
    if not isinstance(key, str) or not key.strip():
        return None
    from apps.pets.models import PetSpecies

    key = key.strip()
    species = PetSpecies.objects.filter(name__iexact=key).first() or PetSpecies.objects.filter(slug=key).first()
    return species.slug if species else None
