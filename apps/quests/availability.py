"""New elemental discoveries require a whole, currently supported hatch pair.

This gate is for new offers only. Accepted goal/quest snapshots continue to
fulfill their saved ingredients after catalog changes.
"""
from apps.rpg.catalog_support import egg_species, item_is_available, pet_is_available, potion_type_for_item


ELEMENTAL_POTIONS = frozenset({"fire", "ice"})


def elemental_potion_ids(items):
    """Resolve the typed potion promise without consulting today's art policy."""
    return {
        item.potion_type_id for item in items
        if item.item_type == "potion" and item.potion_type_id
        and item.potion_type.slug in ELEMENTAL_POTIONS
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
