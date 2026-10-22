"""Read-only image identities; these rules never change acquisition or gameplay.

Only natural content keys and expected receiving-record names/types are public.
PNG paths and bytes are resolved by the private imported manifest in React.
"""
from functools import lru_cache
import json
from pathlib import Path


BINDINGS_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/icon-bindings.json"
ARTWORK_BINDINGS_PATH = BINDINGS_PATH.with_name("artwork-bindings.json")
ELEMENTAL_BINDINGS_PATH = BINDINGS_PATH.with_name("elemental-bindings.json")
ELEMENTAL_EXPANSION_BINDINGS_PATH = BINDINGS_PATH.with_name("elemental-expansion-bindings.json")


@lru_cache(maxsize=1)
def bindings():
    return json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def artwork_bindings():
    return json.loads(ARTWORK_BINDINGS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def elemental_bindings():
    return json.loads(ELEMENTAL_BINDINGS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def elemental_expansion_bindings():
    return json.loads(ELEMENTAL_EXPANSION_BINDINGS_PATH.read_text(encoding="utf-8"))


def badge_catalog_icon(badge):
    if badge is None:
        return None
    entry = artwork_bindings()["badges"].get(badge.name)
    criterion = {"criteria_type": badge.criteria_type, "criteria_value": badge.criteria_value}
    if entry and json.dumps(criterion, sort_keys=True) == json.dumps(entry["expected_criterion"], sort_keys=True):
        return entry["asset_id"]
    return None


def category_catalog_icon(category):
    entry = artwork_bindings()["categories"].get(category.name) if category is not None else None
    return entry["asset_id"] if entry else None


def subject_catalog_icon(subject):
    if subject is None or subject.category is None:
        return None
    entry = artwork_bindings()["subjects"].get(subject.category.name, {}).get(subject.name)
    return entry["asset_id"] if entry else None


def skill_catalog_icon(skill):
    if skill is None or skill.category is None or skill.subject is None:
        return None
    entry = artwork_bindings()["skills"].get(skill.category.name, {}).get(skill.name)
    if entry and skill.subject.category_id == skill.category_id and skill.subject.name == entry["subject"]:
        return entry["asset_id"]
    return None


def item_catalog_icon(item):
    if item is None:
        return None
    elemental = elemental_bindings()["items"].get(item.slug)
    if elemental:
        from apps.pets.roster import prepared_potion

        return elemental["asset_id"] if (item.name == elemental["name"] and prepared_potion(item)
                                         and item.potion_type.slug == elemental["potion_slug"]) else None
    if item.item_type == "egg":
        from apps.rpg.catalog_support import egg_species
        from apps.pets.roster import prepared_family

        family = prepared_family(egg_species(item))
        if family:
            return family["egg"]["portrait_asset_id"]
    entry = bindings()["items"].get(item.slug)
    if entry and item.name == entry["name"] and item.item_type == entry["item_type"]:
        return entry["asset_id"]
    entry = artwork_bindings()["items"].get(item.slug)
    if entry and item.name == entry["identity"]["name"] and item.item_type == entry["identity"]["item_type"]:
        return entry["asset_id"]
    return None


def challenge_catalog_icon(definition):
    if definition is None or not definition.is_system:
        return None
    entry = elemental_bindings()["challenges"].get(definition.name)
    if entry is None:
        entry = elemental_expansion_bindings()["challenges"].get(definition.name)
    if entry and definition.quest_type == entry["quest_type"]:
        return entry["asset_id"]
    entry = bindings()["challenges"].get(definition.name)
    if entry and definition.quest_type == entry["quest_type"]:
        return entry["asset_id"]
    entry = artwork_bindings()["challenges"].get(definition.name)
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
