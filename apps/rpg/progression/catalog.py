"""Read global authoring data once; never inspect a household or mutate a model."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, Skill
from apps.pets.models import PetSpecies
from apps.pets.lifecycle import growth_thresholds
from apps.quests.models import QuestDefinition
from apps.rpg.catalog_support import available_pet_variants, item_is_available
from apps.rpg.models import DropTable, ItemDefinition


MODELED_BADGE_TYPES = frozenset(
    {
        "first_clock_in",
        "hours_worked",
        "hours_in_day",
        "days_worked",
        "skill_level_reached",
        "skills_unlocked",
        "subjects_completed",
        "skill_categories_breadth",
        "cross_category_unlock",
        "category_mastery",
        "streak_days",
        "total_coins_earned",
        "chore_completions",
        "habit_taps_lifetime",
        "habit_max_strength",
        "habit_count_at_strength",
        "badges_earned_count",
        "pets_hatched",
        "pet_species_owned",
        "mounts_evolved",
        "quest_completed",
        "boss_quests_completed",
        "collection_quests_completed",
        "cosmetic_set_owned",
        "journal_entries_written",
        "journal_streak_days",
        "creations_logged",
        "creation_skill_breadth",
        "movement_sessions_logged",
        "movement_total_minutes",
    }
)


@dataclass
class Catalog:
    skills: dict
    items: dict
    pools: dict
    pairs: dict
    badges: list
    quests: list
    excluded_badges: dict
    fingerprint: str

    def summary(self):
        return {
            "fingerprint": self.fingerprint,
            "skills": len(self.skills),
            "supported_items": len(self.items),
            "supported_pet_variants": len(self.pairs),
            "modeled_badges": len(self.badges),
            "excluded_badges": sum(self.excluded_badges.values()),
            "excluded_badge_criteria": self.excluded_badges,
            "system_challenges": len(self.quests),
            "nonrepeatable_challenges": sum(not q.is_repeatable for q in self.quests),
        }


def _bounded(queryset, limit, label):
    rows = list(queryset[: limit + 1])
    if len(rows) > limit:
        raise ValueError(f"Global {label} catalog exceeds the Progression Lab limit ({limit}).")
    return rows


def load_catalog():
    """Only global tables: the simulator intentionally has no user parameter."""
    skills = _bounded(
        Skill.objects.order_by("pk").select_related("category", "subject").prefetch_related("prerequisites"),
        2048,
        "skill",
    )
    items = _bounded(
        ItemDefinition.objects.order_by("pk").select_related("pet_species", "potion_type", "food_species"), 4096, "item"
    )
    items = {item.pk: item for item in items if item_is_available(item)}
    species = _bounded(PetSpecies.objects.order_by("pk").prefetch_related("available_potions"), 256, "species")
    pairs = {(s.pk, p.pk): (s, p) for s in species for p in available_pet_variants(s)}
    pools = {}
    for entry in _bounded(
        DropTable.objects.order_by("pk").select_related("item", "item__pet_species", "item__potion_type"), 16384, "drop"
    ):
        if entry.item_id in items:
            pools.setdefault(entry.trigger_type, []).append(entry)
    badges, excluded = [], Counter()
    for badge in _bounded(Badge.objects.order_by("rarity", "name"), 512, "badge"):
        if badge.criteria_type in MODELED_BADGE_TYPES and badge_goal_is_available(badge):
            badges.append(badge)
        else:
            excluded[badge.criteria_type] += 1
    quests = _bounded(
        QuestDefinition.objects.filter(is_system=True)
        .order_by("pk")
        .prefetch_related("skill_tags__skill", "reward_items__item"),
        256,
        "challenge",
    )
    # A digest of the exact accepted catalog makes a saved forecast comparable.
    serialized = {
        "skills": [
            (
                s.pk,
                s.name,
                s.category_id,
                s.subject_id,
                s.is_locked_by_default,
                [(p.required_skill_id, p.required_level) for p in s.prerequisites.all()],
            )
            for s in skills
        ],
        "items": [
            (
                i.pk,
                i.slug,
                i.item_type,
                i.rarity,
                i.coin_value,
                i.metadata,
                i.pet_species_id,
                i.potion_type_id,
                i.food_species_id,
            )
            for i in items.values()
        ],
        "pairs": [
            (
                key,
                s.slug,
                s.sprite_key,
                s.food_preference,
                growth_thresholds(type("Companion", (), {"species": s, "potion": p})()),
            )
            for key, (s, p) in sorted(pairs.items())
        ],
        "drops": [(e.trigger_type, e.item_id, e.weight, e.min_level) for pool in pools.values() for e in pool],
        "badges": [
            (b.pk, b.name, b.criteria_type, b.criteria_value, b.xp_bonus, b.rarity, b.award_coins) for b in badges
        ],
        "quests": [
            (
                q.pk,
                q.name,
                q.quest_type,
                q.target_value,
                q.duration_days,
                q.trigger_filter,
                q.required_badge_id,
                q.is_repeatable,
                q.xp_reward,
                q.coin_reward,
                [(t.skill_id, t.xp_weight) for t in q.skill_tags.all()],
                [(r.item_id, r.quantity) for r in q.reward_items.all()],
            )
            for q in quests
        ],
    }
    digest = hashlib.sha256(json.dumps(serialized, sort_keys=True, default=str).encode()).hexdigest()
    return Catalog({s.pk: s for s in skills}, items, pools, pairs, badges, quests, dict(excluded), digest)
