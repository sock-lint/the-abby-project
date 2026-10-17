"""Separate supported new offers from server-owned accepted item promises."""
from types import SimpleNamespace

from django.db import transaction


def snapshot_reward_items(definition, *, available_only=True):
    """Freeze item IDs and quantities, retaining the existing response row ID."""
    from apps.rpg.catalog_support import item_is_available

    return [
        {"id": row.pk, "item_id": row.item_id, "quantity": row.quantity}
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
        SimpleNamespace(id=row.get("id"), item_id=row["item_id"], item=item_catalog[row["item_id"]], quantity=row["quantity"])
        for row in rows if row["item_id"] in item_catalog
    ]


@transaction.atomic
def freeze_legacy_quest_promises(*, dry_run=False):
    """Capture retained links once before catalog config can update them."""
    from .models import Quest

    quests = list(Quest.objects.select_for_update(of=("self",)).filter(
        status=Quest.Status.ACTIVE, reward_items_snapshot__isnull=True,
    ).select_related("definition").order_by("pk"))
    if not dry_run:
        for quest in quests:
            # Deliberately preserve updated_at and every progression field.
            Quest.objects.filter(pk=quest.pk, reward_items_snapshot__isnull=True).update(
                reward_items_snapshot=snapshot_reward_items(quest.definition, available_only=False),
            )
    return [quest.pk for quest in quests]
