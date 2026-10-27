"""Reachable collectible goals without changing achievement criteria or payouts."""

from functools import cached_property
import math

from apps.rpg.catalog_support import available_pet_pairs, item_is_available, potion_is_available


_SKILL_LEVEL_GOALS = {
    "skill_level_reached": ("level", 2),
    "subjects_completed": ("min_level", 2),
    "skill_categories_breadth": ("min_level", 1),
    "category_mastery": ("min_level", 3),
}


def native_badge_skill_level(kind, criteria):
    """Return a saved native threshold, or None for an unusable/other criterion.

    The first three native checkers round float thresholds up in their integer
    ORM comparison; mastery converts explicitly with int(). Legacy strings,
    fractions, zero and booleans can remain reachable without changing criteria.
    New content writers retain their independent strict numeric validation.
    """
    if kind not in _SKILL_LEVEL_GOALS or not isinstance(criteria, dict):
        return None
    field, default = _SKILL_LEVEL_GOALS[kind]
    try:
        value = criteria.get(field, default)
        return math.ceil(value) if isinstance(value, float) and kind != "category_mastery" else int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _skill_level_goal_is_reachable(kind, criteria):
    if kind not in _SKILL_LEVEL_GOALS:
        return True
    level = native_badge_skill_level(kind, criteria)
    if level is None:
        return False
    if kind != "category_mastery":
        # These native count comparisons can qualify with no matching rows.
        # Their ORM lookup must still accept the saved level first.
        required = criteria.get("categories", 4) if kind == "skill_categories_breadth" else criteria.get("count", 1)
        if isinstance(required, (int, float)) and required <= 0:
            return True
    from .models import XP_THRESHOLDS
    return level <= max(XP_THRESHOLDS)


class BadgeGoalAvailability:
    """Lazy shared inputs for one read, never cached on a user or across requests."""

    def __init__(self, user=None):
        self.user = user
        self._item_availability = {}
        self._category_ambiguity = {}

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

    def named_category_goal_is_reachable(self, kind, criteria):
        """Hide native category ties without redefining older missing-name rules."""
        if kind not in {"category_projects", "category_mastery"} or not isinstance(criteria, dict):
            return True
        if kind == "category_projects":
            if criteria.get("categories") or criteria.get("category") is None:
                return True
            required = criteria.get("count", 3)
            if isinstance(required, (int, float)) and required <= 0:
                # The native comparison can qualify even with empty resolved IDs.
                return True
        name = criteria.get("category")
        if not isinstance(name, str):
            return True
        key = (kind, name)
        if key not in self._category_ambiguity:
            from .models import SkillCategory
            from .source_identity import project_category_resolution, source_identity_matches
            self._category_ambiguity[key] = (
                project_category_resolution(name).ambiguous if kind == "category_projects"
                else len(source_identity_matches(SkillCategory, {"name": name})) > 1
            )
        return not self._category_ambiguity[key]

    def is_available(self, badge):
        kind = badge.criteria_type
        criteria = badge.criteria_value or {}
        if not _skill_level_goal_is_reachable(kind, criteria):
            # Unusable or genuinely unreachable thresholds stay in earned
            # history without being advertised as a future goal.
            return False
        if not self.named_category_goal_is_reachable(kind, criteria):
            return False
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
