"""Separate supported new offers from server-owned accepted item promises."""
from copy import deepcopy
from types import SimpleNamespace

from django.db import transaction


def egg_reward_is_duplicate(user, item, companion_items):
    """Elemental bundles retain their egg until that exact grown color is owned.

    Existing non-elemental promises keep their established species-wide egg
    salvage. The companion items come from the accepted snapshot, so later
    catalog retirement cannot change which potion the egg was intended for.
    """
    from apps.pets.models import UserMount
    from .availability import elemental_potion_ids

    if item.item_type != "egg" or item.pet_species_id is None:
        return False
    mounts = UserMount.objects.filter(user=user, species_id=item.pet_species_id)
    potion_ids = elemental_potion_ids(companion_items)
    if potion_ids:
        # An egg remains useful if any of the promised elemental forms is new.
        return potion_ids.issubset(set(mounts.values_list("potion_id", flat=True)))
    return mounts.exists()


def reward_item_details(item, *, snapshot=None, cache=None):
    """Describe a reward without changing its accepted identity or payout.

    New promises freeze presentation and effects. Availability always reflects
    today's catalog so a saved reward cannot advertise a retired action.
    Old snapshots can omit the added details; no stored history is rewritten.
    """
    from apps.rpg.catalog_icons import item_catalog_icon
    from apps.rpg.catalog_support import item_is_available
    from apps.rpg.item_effects import effect_summary

    # A challenge list can show the same accepted item in many occurrences
    # and again in recent receipts. Legacy egg metadata may need a database
    # lookup, so reuse its current details only within this one list read.
    if cache is not None and item.pk in cache:
        details = deepcopy(cache[item.pk])
    else:
        details = {
            "item_name": item.display_name, "item_icon": item.icon,
            "item_sprite_key": item.sprite_key, "item_catalog_icon": item_catalog_icon(item),
            "item_rarity": item.rarity, "item_type": item.item_type,
            "item_description": item.description, "item_metadata": deepcopy(item.metadata),
            "item_effect_summary": effect_summary(item),
            "item_catalog_available": item_is_available(item),
        }
        if cache is not None:
            cache[item.pk] = deepcopy(details)
    if snapshot:
        details.update({
            key: deepcopy(snapshot[key]) for key in details
            if key in snapshot and key != "item_catalog_available"
        })
    return details


def snapshot_reward_items(definition, *, available_only=True):
    """Freeze item IDs and quantities, retaining the existing response row ID."""
    from apps.rpg.catalog_support import item_is_available

    return [
        {"id": row.pk, "item_id": row.item_id, "quantity": row.quantity, **reward_item_details(row.item)}
        for row in definition.reward_items.select_related("item__pet_species", "item__potion_type")
        if not available_only or item_is_available(row.item)
    ]


def accepted_reward_items(quest, *, item_catalog=None):
    """Resolve an accepted quest promise without applying today's offer policy.

    Pre-cutover quests have no historical snapshot. Retain their current
    definition links until reconciliation freezes them; reads never write.
    An empty snapshot is a real empty promise, not a legacy fallback.
    """
    from apps.rpg.models import ItemDefinition

    if quest.reward_items_snapshot is None:
        if "reward_items" in getattr(quest.definition, "_prefetched_objects_cache", {}):
            return list(quest.definition.reward_items.all())
        return list(quest.definition.reward_items.select_related("item__pet_species", "item__potion_type"))
    rows = quest.reward_items_snapshot
    if item_catalog is None:
        item_catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
            [row["item_id"] for row in rows],
        )
    return [
        SimpleNamespace(id=row.get("id"), item_id=row["item_id"], item=item_catalog[row["item_id"]],
                        quantity=row["quantity"], reward_snapshot=row)
        for row in rows if row["item_id"] in item_catalog
    ]


@transaction.atomic
def freeze_legacy_quest_promises(*, dry_run=False, definition_ids=None):
    """Capture retained links once before catalog config can update them."""
    from .models import Quest

    queryset = Quest.objects.select_for_update(of=("self",)).filter(
        status=Quest.Status.ACTIVE, reward_items_snapshot__isnull=True,
    )
    if definition_ids is not None:
        queryset = queryset.filter(definition_id__in=definition_ids)
    quests = list(queryset.select_related("definition").order_by("pk"))
    if not dry_run:
        for quest in quests:
            # Deliberately preserve updated_at and every progression field.
            Quest.objects.filter(pk=quest.pk, reward_items_snapshot__isnull=True).update(
                reward_items_snapshot=snapshot_reward_items(quest.definition, available_only=False),
            )
    return [quest.pk for quest in quests]
