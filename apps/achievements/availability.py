"""Reachable collectible goals without changing achievement criteria or payouts."""

from apps.rpg.catalog_support import available_pet_variants, item_is_available, potion_is_available


def badge_goal_is_available(badge, user=None):
    kind = badge.criteria_type
    criteria = badge.criteria_value or {}
    if kind in {"pets_hatched", "pet_species_owned", "mounts_evolved"}:
        from apps.pets.models import PetSpecies, UserMount, UserPet
        pairs = {
            (species.pk, potion.pk)
            for species in PetSpecies.objects.prefetch_related("available_potions")
            for potion in available_pet_variants(species)
        }
        owned_pets = set(UserPet.objects.filter(user=user).values_list("species_id", "potion_id")) if user else set()
        if kind == "pet_species_owned":
            capacity = len({species for species, _potion in pairs | owned_pets})
        elif kind == "mounts_evolved":
            owned_mounts = set(UserMount.objects.filter(user=user).values_list("species_id", "potion_id")) if user else set()
            capacity = len(pairs | owned_pets | owned_mounts)
        else:
            capacity = len(pairs | owned_pets)
        return int(criteria.get("count", 1)) <= capacity
    if kind == "full_potion_shelf":
        from apps.pets.models import PotionType
        from apps.rpg.models import UserInventory
        owned = set(UserInventory.objects.filter(user=user, quantity__gte=1).values_list("item__potion_type_id", flat=True)) if user else set()
        potions = list(PotionType.objects.all())
        return bool(potions) and all(potion_is_available(potion) or potion.pk in owned for potion in potions)
    if kind == "cosmetic_full_set":
        from apps.rpg.models import CharacterProfile, ItemDefinition
        if user and CharacterProfile.objects.filter(user=user, active_pet_accessory__isnull=False).exists():
            return True
        return any(item_is_available(item) for item in ItemDefinition.objects.filter(item_type="cosmetic_pet_accessory"))
    if kind == "cosmetic_set_owned":
        from apps.rpg.models import ItemDefinition, UserInventory
        slugs = set(criteria.get("slugs") or [])
        owned = set(UserInventory.objects.filter(user=user, quantity__gte=1).values_list("item__slug", flat=True)) if user else set()
        items = list(ItemDefinition.objects.filter(slug__in=slugs))
        return bool(slugs) and len(items) == len(slugs) and all(item.slug in owned or item_is_available(item) for item in items)
    return True


def visible_badges(queryset, user):
    from .models import UserBadge
    earned_ids = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    return queryset.filter(pk__in=[badge.pk for badge in queryset if badge.pk in earned_ids or badge_goal_is_available(badge, user)])
