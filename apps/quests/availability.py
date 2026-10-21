"""New elemental discoveries require a whole, currently supported hatch pair.

This gate is for new offers only. Accepted goal/quest snapshots continue to
fulfill their saved ingredients after catalog changes.
"""
from django.db import OperationalError, connection, transaction

from apps.rpg.catalog_support import (
    egg_species, item_is_available, pet_is_available, potion_type_for_item, preload_legacy_references,
)


ELEMENTAL_POTIONS = frozenset({"fire", "ice"})


class RetryCatalogBusy(ValueError):
    """No promise was accepted because reward catalog admission was contended."""


def lock_retry_reward_catalog():
    """Fence item bindings and pair compatibility before taxonomy row locks.

    NOWAIT plus a savepoint releases every partial table lock if a raw catalog
    writer uses another order (including Django's SET_NULL delete collector).
    Accepted predecessor replay never calls this fresh-admission gate.
    """
    if connection.vendor != "postgresql":
        return
    from apps.pets.models import PetSpecies, PotionType
    from apps.rpg.models import ItemDefinition
    tables = sorted(model._meta.db_table for model in (
        PotionType, PetSpecies, ItemDefinition, PetSpecies.available_potions.through,
    ))
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("LOCK TABLE " + ", ".join(connection.ops.quote_name(table) for table in tables)
                               + " IN SHARE MODE NOWAIT")
    except OperationalError as error:
        cause = error.__cause__
        if getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) != "55P03":
            raise
        raise RetryCatalogBusy("Reward catalog is changing. Refresh and try again.") from error


def _snapshot_item_ids(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items", []), list):
        return None
    ids = []
    for row in snapshot.get("items", []):
        if not isinstance(row, dict):
            return None
        item_id, quantity = row.get("item_id"), row.get("quantity")
        if (type(item_id) is not int or not 1 <= item_id <= 9223372036854775807
                or type(quantity) is not int or not 1 <= quantity <= 2147483647):
            return None
        ids.append(item_id)
    return tuple(ids)


def retry_reward_states(occurrences):
    """Batch current availability for the exact saved promises, without writes."""
    from apps.pets.models import PetSpecies, PotionType
    from apps.rpg.models import ItemDefinition
    references = {row.pk: _snapshot_item_ids(row.snapshot) for row in occurrences}
    ids = {item_id for values in references.values() if values is not None for item_id in values}
    catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").prefetch_related(
        "pet_species__available_potions",
    ).in_bulk(ids) if ids else {}
    # Resolve each catalog identity once even when many accepted attempts share
    # ingredients. Typed FK bindings and species compatibility are prefetched.
    legacy_species = (list(PetSpecies.objects.prefetch_related("available_potions"))
                      if any(item.item_type == "egg" and not item.pet_species_id for item in catalog.values()) else None)
    legacy_potions = (list(PotionType.objects.all())
                      if any(item.item_type == "potion" and not item.potion_type_id for item in catalog.values()) else None)
    if legacy_species is not None:
        legacy_species = preload_legacy_references(PetSpecies, legacy_species, [
            item.metadata.get("species") for item in catalog.values() if isinstance(item.metadata, dict)
        ])
    if legacy_potions is not None:
        legacy_potions = preload_legacy_references(PotionType, legacy_potions, [
            item.metadata.get("variant") for item in catalog.values() if isinstance(item.metadata, dict)
        ])
    available = {pk: item_is_available(item, legacy_species=legacy_species, legacy_potions=legacy_potions)
                 for pk, item in catalog.items()}
    species = {pk: egg_species(item, legacy_species=legacy_species)
               for pk, item in catalog.items() if item.item_type == "egg"}
    potions = {pk: potion_type_for_item(item, legacy_potions=legacy_potions)
               for pk, item in catalog.items() if item.item_type == "potion"}
    pairs = {}
    for pk, pet in species.items():
        if pet is None:
            continue
        authored = {potion.pk for potion in pet.available_potions.all()}
        for potion_id, potion in potions.items():
            pairs[pk, potion_id] = (potion is not None and pet_is_available(pet, potion)
                                    and (not authored or potion.pk in authored))
    result = {}
    for pk, values in references.items():
        result[pk] = values is not None and all(available.get(item_id, False) for item_id in values)
        if result[pk]:
            result[pk] = all(pairs.get((egg, potion), False)
                             for egg in values if egg in species for potion in values if potion in potions)
    return result


def promised_potion_ids(items):
    """Every typed potion a companion bundle promises, Base included.

    A bundle's egg stays useful until each promised grown appearance is owned;
    another color of the same species does not make the egg a duplicate.
    """
    return {
        item.potion_type_id for item in items
        if item.item_type == "potion" and item.potion_type_id
    }


def definition_is_available(definition):
    """Keep system Fire/Ice discovery bundles indivisible and exact-pair gated.

    Other definitions retain the existing item-filtering behavior. In
    particular, this does not cancel saved rewards or private parent goals.
    """
    if not definition.is_system:
        return True
    items = [row.item for row in definition.reward_items.all()]
    eggs = [item for item in items if item.item_type == "egg"]
    potions = [item for item in items if item.item_type == "potion" and (
        item.slug in {"fire-potion", "ice-potion"}
        or (item.potion_type_id and item.potion_type.slug in ELEMENTAL_POTIONS)
    )]
    if not eggs or not potions:
        return True
    if not all(item_is_available(item) for item in items):
        return False
    for egg in eggs:
        species = egg_species(egg)
        if species is None:
            return False
        authored = {potion.pk for potion in species.available_potions.all()}
        for ingredient in potions:
            potion = potion_type_for_item(ingredient)
            if (potion is None or not pet_is_available(species, potion)
                    or (authored and potion.pk not in authored)):
                return False
    return True
