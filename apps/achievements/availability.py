"""Reachable collectible goals without changing achievement criteria or payouts."""

from functools import cached_property

from apps.rpg.catalog_support import available_pet_pairs, item_is_available, potion_is_available


class BadgeGoalAvailability:
    """Lazy shared inputs for one read, never cached on a user or across requests."""

    def __init__(self, user=None):
        self.user = user
        self._item_availability = {}

    @cached_property
    def pet_pairs(self):
        return available_pet_pairs()

    @cached_property
    def owned_pets(self):
        from apps.pets.models import UserPet
        return set(UserPet.objects.filter(user=self.user).values_list("species_id", "potion_id")) if self.user else set()

    @cached_property
    def owned_mounts(self):
        from apps.pets.models import UserMount
        return set(UserMount.objects.filter(user=self.user).values_list("species_id", "potion_id")) if self.user else set()

    @cached_property
    def potions(self):
        from apps.pets.models import PotionType
        return list(PotionType.objects.all())

    @cached_property
    def inventory(self):
        from apps.rpg.models import UserInventory
        return list(UserInventory.objects.filter(user=self.user, quantity__gte=1).values_list("item__slug", "item__potion_type_id")) if self.user else []

    @cached_property
    def items(self):
        from apps.rpg.models import ItemDefinition
        return {item.slug: item for item in ItemDefinition.objects.select_related("pet_species", "potion_type")}

    @cached_property
    def has_accessory(self):
        from apps.rpg.models import CharacterProfile
        return bool(self.user and CharacterProfile.objects.filter(user=self.user, active_pet_accessory__isnull=False).exists())

    def item_available(self, item):
        if item.pk not in self._item_availability:
            self._item_availability[item.pk] = item_is_available(item)
        return self._item_availability[item.pk]

    def is_available(self, badge):
        kind = badge.criteria_type
        criteria = badge.criteria_value or {}
        if kind in {"pets_hatched", "pet_species_owned", "mounts_evolved"}:
            pairs = self.pet_pairs | self.owned_pets
            if kind == "pet_species_owned":
                capacity = len({species for species, _potion in pairs})
            elif kind == "mounts_evolved":
                capacity = len(pairs | self.owned_mounts)
            else:
                capacity = len(pairs)
            return int(criteria.get("count", 1)) <= capacity
        if kind == "full_potion_shelf":
            owned = {potion_id for _slug, potion_id in self.inventory}
            return bool(self.potions) and all(potion_is_available(potion) or potion.pk in owned for potion in self.potions)
        if kind == "cosmetic_full_set":
            return self.has_accessory or any(self.item_available(item) for item in self.items.values() if item.item_type == "cosmetic_pet_accessory")
        if kind == "cosmetic_set_owned":
            slugs = set(criteria.get("slugs") or [])
            owned = {slug for slug, _potion_id in self.inventory}
            return bool(slugs) and all(
                slug in self.items and (slug in owned or self.item_available(self.items[slug]))
                for slug in slugs
            )
        return True


def availability_for_request(request):
    """Share visibility/serializer inputs only within this authenticated read."""
    if not hasattr(request, "_badge_goal_availability"):
        request._badge_goal_availability = BadgeGoalAvailability(request.user)
    return request._badge_goal_availability


def badge_goal_is_available(badge, user=None):
    # Service callers may evaluate again after mutating ownership or catalog
    # state; only an explicit read context may reuse a snapshot.
    return BadgeGoalAvailability(user).is_available(badge)


def visible_badges(queryset, user, *, availability=None):
    from .models import UserBadge
    availability = availability or BadgeGoalAvailability(user)
    earned_ids = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    return queryset.filter(pk__in=[badge.pk for badge in queryset if badge.pk in earned_ids or availability.is_available(badge)])
