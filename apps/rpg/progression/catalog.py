"""Read global authoring data once; never inspect a household or mutate a model."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, Skill
from apps.pets.models import PetSpecies
from apps.pets.lifecycle import growth_thresholds
from apps.quests.models import QuestDefinition
from apps.rpg.catalog_support import available_pet_variants, egg_species, item_is_available, potion_type_for_item, random_item_is_available
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


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenRows(_freeze(item) for item in value)
    return value


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class FrozenRows(tuple):
    """Eager relation values with the small read interface used by domain helpers."""

    def all(self):
        return self

    def exists(self):
        return bool(self)


@dataclass(frozen=True)
class CatalogRecord:
    """A detached immutable record, never a model or related manager."""

    fields: Mapping

    def __getattr__(self, name):
        try:
            return self.fields[name]
        except KeyError:
            raise AttributeError(name) from None


def _record(model, **relations):
    fields = {field.attname: getattr(model, field.attname) for field in model._meta.concrete_fields}
    fields.update(pk=model.pk, **relations)
    return CatalogRecord(_freeze(fields))


@dataclass(frozen=True)
class Catalog:
    skills: dict
    items: dict
    pools: dict
    pairs: dict
    badges: list
    quests: list
    excluded_badges: dict
    fingerprint: str

    def __post_init__(self):
        for name in ("skills", "items", "pools", "pairs", "badges", "quests", "excluded_badges"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))

    def summary(self):
        return {
            "fingerprint": self.fingerprint,
            "skills": len(self.skills),
            "supported_items": len(self.items),
            "supported_pet_variants": len(self.pairs),
            "modeled_badges": len(self.badges),
            "excluded_badges": sum(self.excluded_badges.values()),
            "excluded_badge_criteria": dict(self.excluded_badges),
            "system_challenges": len(self.quests),
            "nonrepeatable_challenges": sum(not q.is_repeatable for q in self.quests),
        }


def _bounded(queryset, limit, label):
    rows = list(queryset[: limit + 1])
    if len(rows) > limit:
        raise ValueError(f"Global {label} catalog exceeds the Progression Lab limit ({limit}).")
    return rows


def snapshot_catalog():
    """Capture global rules as detached immutable values, safe after a rollback.

    A publication preview can call this while proposed rows exist in its
    savepoint, roll them back, then simulate without any subsequent ORM reads.
    No account, family, inventory, ledger or reward writer is involved.
    """
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
        if entry.item_id in items and random_item_is_available(entry.item):
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
    # Detach the entire graph, including every relation consumed by pure rules.
    species_records = {
        s.pk: _record(s, available_potions=FrozenRows(_record(p) for p in s.available_potions.all()))
        for s in species
    }
    pairs = {
        key: (species_records[s.pk], _record(p)) for key, (s, p) in pairs.items()
    }
    skill_records = {
        s.pk: _record(s, category=_record(s.category),
                      prerequisites=FrozenRows(_record(p) for p in s.prerequisites.all()))
        for s in skills
    }
    item_records = {}
    for item in items.values():
        species_ref = egg_species(item) if item.item_type == "egg" else item.pet_species
        potion_ref = potion_type_for_item(item) if item.item_type == "potion" else item.potion_type
        item_records[item.pk] = _record(
            item, display_name=item.display_name,
            pet_species=species_records.get(species_ref.pk) if species_ref else None,
            pet_species_id=species_ref.pk if species_ref else None,
            potion_type=_record(potion_ref) if potion_ref else None,
            potion_type_id=potion_ref.pk if potion_ref else None,
            food_species=species_records.get(item.food_species_id),
        )
    pools = {trigger: FrozenRows(_record(e, item=item_records[e.item_id]) for e in pool)
             for trigger, pool in pools.items()}
    quests = FrozenRows(_record(
        q, skill_tags=FrozenRows(_record(t, skill=skill_records[t.skill_id]) for t in q.skill_tags.all()),
        reward_items=FrozenRows(_record(r) for r in q.reward_items.all()),
    ) for q in quests)
    badges = FrozenRows(_record(b) for b in badges)
    skills, items = list(skill_records.values()), item_records
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
                q.prerequisite_quest_id,
                q.required_skill_id,
                q.required_skill_level,
                q.is_repeatable,
                q.xp_reward,
                q.coin_reward,
                [(t.skill_id, t.xp_weight) for t in q.skill_tags.all()],
                [(r.item_id, r.quantity) for r in q.reward_items.all()],
            )
            for q in quests
        ],
    }
    digest = hashlib.sha256(json.dumps(_plain(serialized), sort_keys=True, default=str).encode()).hexdigest()
    return Catalog({s.pk: s for s in skills}, items, pools, pairs, badges, quests, dict(excluded), digest)


def load_catalog():
    """Compatibility name for callers that need the current global snapshot."""
    return snapshot_catalog()
