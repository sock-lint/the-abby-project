"""Remove the owner's explicitly retired, unused first-party content identities.

This list is deliberately independent of artwork availability. Fire and Ice are
planned content; a temporary art-policy hold must never turn into deletion.
No account, ledger balance, SpriteAsset row or stored artwork is removed.
"""
from django.db import transaction
from django.db.models import Q


RETIRED_SPECIES = {
    "wolf": "Wolf", "dragon": "Dragon", "fox": "Fox", "owl": "Owl",
    "cat": "Cat", "bear": "Bear", "phoenix": "Phoenix", "unicorn": "Unicorn",
    "clownling": "Clownling", "pondshell": "Pondshell", "seafang": "Seafang",
    "ripplecoil": "Ripplecoil", "drift-jelly": "Drift Jelly", "deepkraken": "Deepkraken",
    "stallion": "Stallion", "archdragon": "Archdragon", "companion": "Companion",
}
RETIRED_POTIONS = {"shadow": "Shadow", "golden": "Golden", "cosmic": "Cosmic"}
RETIRED_SPECIES_SPRITES = {
    **{slug: slug for slug in RETIRED_SPECIES},
    "seafang": "tropical-fish", "ripplecoil": "eel", "drift-jelly": "jellyfish",
    "deepkraken": "octopus", "stallion": "horse",
}
RETIRED_ACCESSORIES = {
    "accessory-party-hat": "Party Hat", "accessory-bow-tie": "Bow Tie", "accessory-crown": "Crown",
    "accessory-prayer-beads": "Prayer Beads", "accessory-silver-ring": "Silver Ring",
    "accessory-tribal-necklace": "Tribal Necklace", "accessory-gold-necklace": "Gold Necklace",
    "accessory-diamond-ring": "Diamond Ring", "accessory-sunglasses": "Sunglasses",
    "accessory-wizard-hat": "Wizard Hat", "accessory-flower-crown": "Flower Crown",
    "accessory-tiny-cape": "Tiny Cape", "accessory-bandana": "Bandana",
    "accessory-armor-plate": "Armor Plate", "accessory-celestial-halo": "Celestial Halo",
    "accessory-backpack-charm": "Lucky Backpack Charm", "accessory-party-horn": "Party Horn",
    # One optional pack was actually loaded with this exact namespace. Do not
    # infer other namespaces from the raw authoring key.
    "hs-prep-2026-accessory-backpack-charm": "Lucky Backpack Charm",
}
RETIRED_ITEMS = {
    **{f"{slug}-egg": (f"{name} Egg", "egg") for slug, name in RETIRED_SPECIES.items()},
    **{f"{slug}-potion": (f"{name} Potion", "potion") for slug, name in RETIRED_POTIONS.items()},
    **{slug: (name, "cosmetic_pet_accessory") for slug, name in RETIRED_ACCESSORIES.items()},
}


class RetiredCatalogCollision(ValueError):
    """An expected obsolete slug now identifies different authored content."""


def _without_item_slots(value, item_ids):
    if not isinstance(value, list):
        return value
    return [slot for slot in value if not isinstance(slot, dict)
            or type(slot.get("item_id")) is not int or slot["item_id"] not in item_ids]


@transaction.atomic
def retire_unused_catalog(*, dry_run=False):
    """Atomically discard only the retired identities and their dependencies.

    Protected incubation/redemption receipts are intentionally discarded for
    these unused identities. Supported, planned and unknown/custom identities
    keep their ownership and promises. Dry runs execute the same path under a
    rolled-back savepoint, including cascades and snapshot pruning.
    """
    from apps.pets.models import MountExpedition, PetIncubation, PetSpecies, PotionType, UserMount, UserPet
    from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestRewardItem
    from apps.rewards.models import Reward, RewardRedemption
    from .content.publication import _catalog_lock
    from .models import CharacterProfile, ContentPackEntry, DropTable, ItemDefinition, RPGContentOverride

    _catalog_lock()
    species = list(PetSpecies.objects.select_for_update().filter(slug__in=RETIRED_SPECIES).order_by("pk"))
    potions = list(PotionType.objects.select_for_update().filter(slug__in=RETIRED_POTIONS).order_by("pk"))
    items = list(ItemDefinition.objects.select_for_update().filter(slug__in=RETIRED_ITEMS).order_by("pk"))
    for row in [*species, *potions]:
        expected = (RETIRED_SPECIES if isinstance(row, PetSpecies) else RETIRED_POTIONS)[row.slug]
        if row.name != expected:
            raise RetiredCatalogCollision(f"Retired identity {row._meta.label_lower} id={row.pk} has a different name; reconcile it before cleanup.")
        if isinstance(row, PetSpecies) and row.sprite_key != RETIRED_SPECIES_SPRITES[row.slug]:
            raise RetiredCatalogCollision(f"Retired species id={row.pk} slug={row.slug} has different artwork; reconcile it before cleanup.")
    for item in items:
        if (item.name, item.item_type) != RETIRED_ITEMS[item.slug]:
            raise RetiredCatalogCollision(f"Retired item id={item.pk} slug={item.slug} has a different identity; reconcile it before cleanup.")
        expected_slug = item.slug.removesuffix("-egg" if item.item_type == "egg" else "-potion")
        reference = item.pet_species if item.item_type == "egg" else item.potion_type if item.item_type == "potion" else None
        if reference is not None and reference.slug != expected_slug:
            raise RetiredCatalogCollision(f"Retired item id={item.pk} slug={item.slug} references different content; reconcile it before cleanup.")

    species_ids, potion_ids, item_ids = {row.pk for row in species}, {row.pk for row in potions}, {row.pk for row in items}
    care_filter = Q(species_id__in=species_ids) | Q(potion_id__in=potion_ids)
    pets = UserPet.objects.filter(care_filter)
    mounts = UserMount.objects.filter(care_filter)
    pet_ids, mount_ids = set(pets.values_list("pk", flat=True)), set(mounts.values_list("pk", flat=True))
    incubations = PetIncubation.objects.filter(
        Q(species_id__in=species_ids) | Q(potion_type_id__in=potion_ids)
        | Q(egg_item_id__in=item_ids) | Q(potion_item_id__in=item_ids),
    )
    # Real-world offers may happen to carry an unused item FK. Retain them;
    # ItemDefinition deletion clears that optional reference. Retire digital
    # offers and exact frozen item promises without touching their coin rows.
    offers = Reward.objects.filter(item_definition_id__in=item_ids).exclude(fulfillment_kind="real_world")
    offer_ids = set(offers.values_list("pk", flat=True))
    redemptions = RewardRedemption.objects.filter(item_definition_snapshot_id__in=item_ids)
    # An edited offer can have an older supported frozen promise. Keep that
    # receipt and its required offer row, deactivating only the obsolete offer.
    retained_offer_ids = set(RewardRedemption.objects.filter(reward_id__in=offer_ids).exclude(
        pk__in=redemptions.values("pk"),
    ).values_list("reward_id", flat=True))
    deletable_offers = offers.exclude(pk__in=retained_offer_ids)
    report = {
        "dry_run": dry_run,
        "species": [{"id": row.pk, "slug": row.slug} for row in species],
        "potions": [{"id": row.pk, "slug": row.slug} for row in potions],
        "items": [{"id": row.pk, "slug": row.slug, "item_type": row.item_type} for row in items],
        "pet_ids": sorted(pet_ids), "mount_ids": sorted(mount_ids),
        "incubation_ids": list(incubations.order_by("pk").values_list("pk", flat=True)),
        "offer_ids": sorted(offer_ids), "retained_offer_ids": sorted(retained_offer_ids),
        "redemption_ids": list(redemptions.order_by("pk").values_list("pk", flat=True)),
        "cleared_food_item_ids": list(ItemDefinition.objects.filter(food_species_id__in=species_ids).order_by("pk").values_list("pk", flat=True)),
        "cleared_equipped_profile_ids": list(CharacterProfile.objects.filter(
            Q(active_frame_id__in=item_ids) | Q(active_title_id__in=item_ids)
            | Q(active_theme_id__in=item_ids) | Q(active_pet_accessory_id__in=item_ids),
        ).order_by("pk").values_list("pk", flat=True)),
        "quest_snapshot_ids": [], "goal_reward_ids": [], "occurrence_snapshot_ids": [],
        "occurrence_receipt_ids": [], "expedition_loot_ids": [], "growth_queue_profile_ids": [],
        "deleted": {},
    }

    # Snapshots are JSON rather than foreign keys. Preserve all unrelated
    # entries, coins, quantities, timestamps and progress while pruning slots.
    if item_ids:
        for quest in Quest.objects.exclude(reward_items_snapshot__isnull=True).iterator():
            cleaned = _without_item_slots(quest.reward_items_snapshot, item_ids)
            if cleaned != quest.reward_items_snapshot:
                Quest.objects.filter(pk=quest.pk).update(reward_items_snapshot=cleaned)
                report["quest_snapshot_ids"].append(quest.pk)
        for goal in ChallengeGoal.objects.exclude(reward_items=[]).iterator():
            cleaned = _without_item_slots(goal.reward_items, item_ids)
            if cleaned != goal.reward_items:
                ChallengeGoal.objects.filter(pk=goal.pk).update(reward_items=cleaned)
                report["goal_reward_ids"].append(goal.pk)
        for occurrence in ChallengeOccurrence.objects.iterator():
            changes = {}
            for field, report_field in (("snapshot", "occurrence_snapshot_ids"), ("reward_receipt", "occurrence_receipt_ids")):
                value = getattr(occurrence, field)
                if isinstance(value, dict):
                    cleaned = _without_item_slots(value.get("items"), item_ids)
                    if cleaned != value.get("items"):
                        changes[field] = {**value, "items": cleaned}
                        report[report_field].append(occurrence.pk)
            if changes:
                ChallengeOccurrence.objects.filter(pk=occurrence.pk).update(**changes)
        for expedition in MountExpedition.objects.exclude(mount_id__in=mount_ids).iterator():
            if not isinstance(expedition.loot, dict):
                continue
            cleaned = _without_item_slots(expedition.loot.get("items"), item_ids)
            if cleaned != expedition.loot.get("items"):
                MountExpedition.objects.filter(pk=expedition.pk).update(loot={**expedition.loot, "items": cleaned})
                report["expedition_loot_ids"].append(expedition.pk)
    profiles = (CharacterProfile.objects.exclude(pending_companion_growth=[])
                if species_ids or potion_ids else CharacterProfile.objects.none())
    for profile in profiles.iterator():
        pending = profile.pending_companion_growth
        if not isinstance(pending, list):
            continue
        cleaned = [event for event in pending if not isinstance(event, dict) or not (
            event.get("pet_id") in pet_ids or event.get("mount_id") in mount_ids
            or event.get("species_slug") in RETIRED_SPECIES or event.get("potion_slug") in RETIRED_POTIONS
        )]
        if cleaned != pending:
            CharacterProfile.objects.filter(pk=profile.pk).update(pending_companion_growth=cleaned)
            report["growth_queue_profile_ids"].append(profile.pk)

    def delete(queryset):
        _total, counts = queryset.delete()
        for label, count in counts.items():
            report["deleted"][label] = report["deleted"].get(label, 0) + count

    # Clear non-FK authoring ownership for the exact removed catalog rows.
    removed_offer_ids = offer_ids - retained_offer_ids
    drop_ids = DropTable.objects.filter(item_id__in=item_ids).values_list("pk", flat=True)
    quest_link_ids = QuestRewardItem.objects.filter(item_id__in=item_ids).values_list("pk", flat=True)
    ownership_filter = (Q(model_label="pets.petspecies", object_id__in=species_ids)
                        | Q(model_label="pets.potiontype", object_id__in=potion_ids)
                        | Q(model_label="rpg.itemdefinition", object_id__in=item_ids)
                        | Q(model_label="rewards.reward", object_id__in=removed_offer_ids)
                        | Q(model_label="rpg.droptable", object_id__in=drop_ids)
                        | Q(model_label="quests.questrewarditem", object_id__in=quest_link_ids))
    delete(ContentPackEntry.objects.filter(ownership_filter))
    delete(RPGContentOverride.objects.filter(ownership_filter))
    delete(incubations)
    delete(redemptions)
    offers.filter(pk__in=retained_offer_ids).update(is_active=False)
    delete(deletable_offers)
    delete(ItemDefinition.objects.filter(pk__in=item_ids))
    delete(PetSpecies.objects.filter(pk__in=species_ids))
    delete(PotionType.objects.filter(pk__in=potion_ids))
    if dry_run:
        transaction.set_rollback(True)
    return report
