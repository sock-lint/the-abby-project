"""Preserve saved content while retiring unsupported acquisition offers."""
from collections import defaultdict
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction

from apps.pets.roster import FAMILIES
from .catalog_support import egg_species, item_is_available


# The previous production pool had one common Chick egg, authored weight 10.
# Fifteen equally weighted family eggs share that same category budget.
EGG_CATEGORY_WEIGHT = 10


class CompanionCatalogCollision(ValueError):
    """An existing receiving identity needs operator reconciliation."""


def check_prepared_identity_collisions():
    """Never repair a conflicting identity by rewriting its saved references."""
    from apps.pets.models import PetSpecies
    from .models import ItemDefinition

    conflicts = []
    receiving = dict(FAMILIES)
    if getattr(settings, "RPG_ASSET_SUPPORT_POLICY", None) is None:
        receiving["chick"] = {
            "name": "Chick", "sprite_key": "cute-chick", "egg": {"item_slug": "chick-egg"},
        }
    for slug, family in receiving.items():
        species = PetSpecies.objects.filter(slug=slug).first()
        name_collision = PetSpecies.objects.filter(name__iexact=family["name"]).exclude(slug=slug).first()
        if name_collision:
            conflicts.append(f"species id={name_collision.pk} display-name collision for {slug}")
        if species and (species.name != family["name"] or species.sprite_key != family["sprite_key"]):
            conflicts.append(f"species id={species.pk} identity collision for {slug}")
        egg = ItemDefinition.objects.filter(slug=family["egg"]["item_slug"]).first()
        if egg:
            metadata = egg.metadata if isinstance(egg.metadata, dict) else {}
            if (species is None or egg.item_type != "egg" or egg.pet_species_id != species.pk
                    or metadata.get("species") != slug):
                conflicts.append(f"egg id={egg.pk} typed/metadata identity collision for {egg.slug}")
    if conflicts:
        raise CompanionCatalogCollision("; ".join(conflicts))


def companion_drop_weights(entries, weights=None, *, category_weight=EGG_CATEGORY_WEIGHT):
    """Keep production egg odds stable; leave other/custom/synthetic rows alone.

    Apply once after any expedition rarity bias. Each trigger retains the
    previous egg category weight, so a fallback union keeps both budgets.
    """
    result = list(weights if weights is not None else (entry.weight for entry in entries))
    if getattr(settings, "RPG_ASSET_SUPPORT_POLICY", None) is not None:
        return result
    groups = defaultdict(list)
    for index, entry in enumerate(entries):
        if entry.item.item_type != "egg":
            continue
        species = egg_species(entry.item)
        if species is None:
            continue
        family = FAMILIES.get(species.slug)
        canonical = family["egg"]["item_slug"] if family else "chick-egg" if species.slug == "chick" else None
        if canonical and entry.item.slug == canonical and item_is_available(entry.item):
            groups[entry.trigger_type].append(index)
    for indices in groups.values():
        source_total = sum(entries[index].weight for index in indices)
        effective_total = sum(result[index] for index in indices)
        if source_total > 0 and effective_total > 0:
            # The weighted mean preserves an existing expedition rarity bias.
            target = category_weight * effective_total / source_total
            for index in indices:
                result[index] = result[index] * target / effective_total
    return result


def companion_item_weights(items, weights):
    """Mystery pools previously contained one eligible common egg (weight 5)."""
    entries = [SimpleNamespace(item=item, weight=1, trigger_type="item_pool") for item in items]
    return companion_drop_weights(entries, weights, category_weight=1)


@transaction.atomic
def reconcile_companion_offers(*, dry_run=False):
    """Retire acquisition configuration only; keep all identities and promises."""
    from apps.quests.models import QuestRewardItem
    from apps.rewards.models import Reward
    from .models import DropTable, ItemDefinition

    check_prepared_identity_collisions()

    items = [item for item in ItemDefinition.objects.filter(
        item_type__in=["egg", "potion"],
    ).select_related("pet_species", "potion_type").order_by("pk") if not item_is_available(item)]
    ids = [item.pk for item in items]
    drops = DropTable.objects.filter(item_id__in=ids)
    offers = Reward.objects.filter(
        item_definition_id__in=ids, is_active=True,
        fulfillment_kind__in=[Reward.FulfillmentKind.DIGITAL_ITEM, Reward.FulfillmentKind.BOTH],
    )
    report = {
        "dry_run": dry_run,
        "drops_removed": drops.count(),
        "rewards_deactivated": offers.count(),
        "retained_quest_reward_links": QuestRewardItem.objects.filter(item_id__in=ids).count(),
        "item_slugs": [item.slug for item in items],
        "items": [{"id": item.pk, "slug": item.slug, "item_type": item.item_type} for item in items],
        "drop_ids": list(drops.order_by("pk").values_list("pk", flat=True)),
        "reward_ids": list(offers.order_by("pk").values_list("pk", flat=True)),
    }
    if not dry_run:
        drops.delete()
        offers.update(is_active=False)
    return report
