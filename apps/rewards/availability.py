from apps.rpg.catalog_support import item_is_available


def reward_is_available(reward, *, legacy_species=None, legacy_potions=None):
    """New shop requests must deliver an item supported by the current app."""
    if reward.fulfillment_kind == "real_world":
        return True
    return reward.item_definition_id is not None and item_is_available(
        reward.item_definition, legacy_species=legacy_species, legacy_potions=legacy_potions,
    )


def available_rewards(queryset):
    ids = [reward.pk for reward in queryset.select_related("item_definition") if reward_is_available(reward)]
    return queryset.filter(pk__in=ids)
