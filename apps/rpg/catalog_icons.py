"""Read-only image identities; these rules never change acquisition or gameplay.

Only natural content keys and expected receiving-record names/types are public.
PNG paths and bytes are resolved by the private imported manifest in React.
"""
from functools import lru_cache
import json
from pathlib import Path


BINDINGS_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/icon-bindings.json"


@lru_cache(maxsize=1)
def bindings():
    return json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))


def item_catalog_icon(item):
    if item is None:
        return None
    if item.item_type == "egg":
        from apps.rpg.catalog_support import egg_species
        from apps.pets.roster import prepared_family

        family = prepared_family(egg_species(item))
        if family:
            return family["egg"]["portrait_asset_id"]
    entry = bindings()["items"].get(item.slug)
    if entry and item.name == entry["name"] and item.item_type == entry["item_type"]:
        return entry["asset_id"]
    return None


def challenge_catalog_icon(definition):
    if definition is None or not definition.is_system:
        return None
    entry = bindings()["challenges"].get(definition.name)
    if entry and definition.quest_type == entry["quest_type"]:
        return entry["asset_id"]
    return None


def species_catalog_icon(species, *, grown=False):
    if species is None:
        return None
    from apps.pets.roster import prepared_family

    family = prepared_family(species)
    if family and species.name == family["name"]:
        return family["stages"]["grown" if grown else "baby"]["portrait_asset_id"]
    entry = bindings()["pets"].get(species.slug)
    if entry and species.name == entry["name"] and species.sprite_key == entry["sprite_key"]:
        return entry["grown_catalog_icon" if grown else "catalog_icon"]
    return None
