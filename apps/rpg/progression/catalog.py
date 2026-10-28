"""Read global authoring data once; never inspect a household or mutate a model."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType

from apps.achievements.availability import BadgeGoalAvailability
from apps.achievements.models import Badge, Skill, SkillCategory
from apps.pets.models import PetSpecies
from apps.pets.lifecycle import growth_thresholds
from apps.quests.queries import active_system_definitions
from apps.rpg.catalog_support import available_pet_variants, egg_species, item_is_available, potion_type_for_item, random_item_is_available
from apps.rpg.models import DropTable, ItemDefinition, RPGContentOverride


TAXONOMY_CATEGORY_LIMIT = 2048
TAXONOMY_OVERRIDE_LIMIT = 4096


def taxonomy_source_overrides():
    """Only global taxonomy provenance consumed by the installed resolver.

    Leave projection to the caller: snapshots copy only the source identity,
    while decision freshness can compare PostgreSQL row versions. Neither
    consumer needs an author's family, publication or replacement values.
    Database JSON equality also keeps boolean versions distinct from version 1.
    """
    return RPGContentOverride.objects.filter(
        model_label__in=(SkillCategory._meta.label_lower, Skill._meta.label_lower),
        values___authoring={"version": 1, "source": "mcp"},
    ).order_by("pk")


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
    source_categories: Mapping = field(default_factory=dict)
    source_skills: Mapping = field(default_factory=dict)

    def __post_init__(self):
        for name in ("skills", "items", "pools", "pairs", "badges", "quests", "excluded_badges",
                     "source_categories", "source_skills"):
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


def _taxonomy_identities(categories, skills):
    """Detach unique current-or-retained identities without per-row ORM reads.

    This mirrors ``resolve_source_identity`` for its complete category and
    category-qualified skill lookups. Competing objects fail closed, including
    empty current categories. Retired rows remain installed destinations.
    """
    category_matches, skill_matches = defaultdict(set), defaultdict(set)
    category_ids = {pk for pk, _ in categories}
    skill_ids = {skill.pk for skill in skills}
    for pk, name in categories:
        category_matches[name].add(pk)
    for skill in skills:
        skill_matches[(skill.category_id, skill.name)].add(skill.pk)
    overrides = _bounded(
        taxonomy_source_overrides().values("model_label", "object_id", "source_lookup"),
        TAXONOMY_OVERRIDE_LIMIT, "taxonomy source",
    )
    for row in overrides:
        lookup, object_id = row["source_lookup"], row["object_id"]
        if type(lookup) is not dict or type(lookup.get("name")) is not str:
            continue
        if row["model_label"] == SkillCategory._meta.label_lower:
            if set(lookup) == {"name"} and object_id in category_ids:
                category_matches[lookup["name"]].add(object_id)
        elif (set(lookup) == {"name", "category_id"} and type(lookup["category_id"]) is int
              and object_id in skill_ids):
            skill_matches[(lookup["category_id"], lookup["name"])].add(object_id)
    def unique(matches):
        return {key: next(iter(ids)) if len(ids) == 1 else None for key, ids in matches.items()}
    return unique(category_matches), unique(skill_matches)


def snapshot_catalog():
    """Capture global rules as detached immutable values, safe after a rollback.

    A publication preview can call this while proposed rows exist in its
    savepoint, roll them back, then simulate without any subsequent ORM reads.
    No account, family, inventory, ledger or reward writer is involved.
    """
    categories = _bounded(
        SkillCategory.objects.order_by("pk").values_list("pk", "name"), TAXONOMY_CATEGORY_LIMIT, "category",
    )
    skills = _bounded(
        Skill.objects.order_by("pk").select_related("category", "subject__category").prefetch_related("prerequisites"),
        2048,
        "skill",
    )
    source_categories, source_skills = _taxonomy_identities(categories, skills)
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
    badge_rows = _bounded(Badge.objects.order_by("rarity", "name"), 512, "badge")
    availability = BadgeGoalAvailability()
    availability.prepare_named_categories(badge for badge in badge_rows if badge.criteria_type in MODELED_BADGE_TYPES)
    for badge in badge_rows:
        if badge.criteria_type in MODELED_BADGE_TYPES and availability.is_available(badge):
            badges.append(badge)
        else:
            excluded[badge.criteria_type] += 1
    from apps.quests.reference_locks import definitions_with_available_taxonomy
    from apps.quests.availability import definition_is_available
    quests = _bounded(
        definitions_with_available_taxonomy(active_system_definitions()).filter(is_cooperative=False)
        .order_by("pk")
        .prefetch_related("skill_tags__skill", "reward_items__item__pet_species__available_potions", "reward_items__item__potion_type"),
        256,
        "challenge",
    )
    quests = [q for q in quests if definition_is_available(q)]
    # Detach the entire graph, including every relation consumed by pure rules.
    species_records = {
        s.pk: _record(s, available_potions=FrozenRows(_record(p) for p in s.available_potions.all()))
        for s in species
    }
    pairs = {
        key: (species_records[s.pk], _record(p)) for key, (s, p) in pairs.items()
    }
    from apps.achievements.taxonomy import available_for_new_choices
    skill_records = {
        s.pk: _record(s, category=_record(s.category),
                      available_for_new_choices=available_for_new_choices(s),
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
        "categories": categories,
        "source_categories": sorted(source_categories.items()),
        "source_skills": [(category_id, name, skill_id)
                          for (category_id, name), skill_id in sorted(source_skills.items())],
        "skills": [
            (
                s.pk,
                s.name,
                s.category_id,
                s.subject_id,
                s.is_locked_by_default,
                s.is_retired,
                s.available_for_new_choices,
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
    return Catalog({s.pk: s for s in skills}, items, pools, pairs, badges, quests, dict(excluded), digest,
                   source_categories, source_skills)


def load_catalog():
    """Compatibility name for callers that need the current global snapshot."""
    return snapshot_catalog()
