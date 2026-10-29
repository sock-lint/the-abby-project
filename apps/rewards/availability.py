from apps.rpg.catalog_support import item_is_available
from apps.egg_discoveries.policy import legacy_egg_acquisition_allowed


def reward_is_available(reward):
    """New shop requests must deliver an item supported by the current app."""
    if reward.fulfillment_kind == "real_world":
        return True
    return (reward.item_definition_id is not None
            and legacy_egg_acquisition_allowed(reward.item_definition)
            and item_is_available(reward.item_definition))


def available_rewards(queryset):
    ids = [reward.pk for reward in queryset.select_related("item_definition") if reward_is_available(reward)]
    return queryset.filter(pk__in=ids)
