"""Tier budgets stay stable as catalogs grow; authored weights choose within tiers.

    Budgets describe a successful draw, not the chance an activity drops loot.
    Absent/empty tiers are renormalized over the remaining positive tiers.
"""
from collections import defaultdict

BASE_TIER_WEIGHTS = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}
ACCOMPLISHMENT_TIER_WEIGHTS = {"common": 40, "uncommon": 30, "rare": 20, "epic": 8, "legendary": 2}
MYSTERY_TIER_WEIGHTS = {"common": 70, "uncommon": 30}
LUCKY_DIP_TIER_WEIGHTS = {"common": 0, "uncommon": 60, "rare": 30, "epic": 10, "legendary": 1}
ACCOMPLISHMENT_TRIGGERS = {"milestone_complete", "project_complete", "badge_earned", "quest_complete", "perfect_day", "savings_goal_complete"}
COSMETIC_TYPES = {"cosmetic_frame", "cosmetic_title", "cosmetic_theme", "cosmetic_pet_accessory"}


def drop_tier_weights(trigger_type):
    """Successful-draw budgets, including Perfect Day's Uncommon floor."""
    weights = dict(ACCOMPLISHMENT_TIER_WEIGHTS if trigger_type in ACCOMPLISHMENT_TRIGGERS else BASE_TIER_WEIGHTS)
    if trigger_type == "perfect_day":
        weights["common"] = 0
    return weights


def tier_balanced_weights(entries, tier_weights, *, authored_weights=None, owned_item_ids=()):
    """Return one weight per entry without another random roll.

    New cosmetics receive a tier's cosmetic weight before owned duplicates.
    This preserves both tier odds and the cosmetic category's total weight;
    fully collected tiers retain their existing salvage path. Callers filter
    permissions, level and supported art before using this selector.
    """
    items = [getattr(entry, "item", entry) for entry in entries]
    weights = list(authored_weights if authored_weights is not None else (entry.weight for entry in entries))
    owned = set(owned_item_ids)
    groups = defaultdict(list)
    for index, item in enumerate(items):
        if weights[index] > 0 and tier_weights.get(item.rarity, 0) > 0:
            groups[item.rarity].append(index)
        else:
            weights[index] = 0
    for rarity, indices in groups.items():
        cosmetics = [i for i in indices if items[i].item_type in COSMETIC_TYPES]
        unowned = [i for i in cosmetics if items[i].pk not in owned]
        if unowned:
            cosmetic_total = sum(weights[i] for i in cosmetics)
            unowned_total = sum(weights[i] for i in unowned)
            for i in cosmetics:
                weights[i] = weights[i] * cosmetic_total / unowned_total if i in unowned else 0
        total = sum(weights[i] for i in indices)
        for i in indices:
            weights[i] = tier_weights[rarity] * weights[i] / total
    return weights


def owned_cosmetic_ids(user):
    from .models import UserInventory
    return set(UserInventory.objects.filter(
        user=user, quantity__gt=0, item__item_type__in=COSMETIC_TYPES,
    ).values_list("item_id", flat=True))
