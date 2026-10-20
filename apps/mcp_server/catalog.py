"""Read-only global catalog projections and bounded structural audits.

Availability describes new acquisition, without any player's saved inventory or
earned badges. Unsupported retained definitions are reported, never rewritten.
"""
from django.core.exceptions import ValidationError

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, Subject, XP_THRESHOLDS
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition
from apps.quests.queries import active_system_definitions
from apps.quests.validators import validate_trigger_filter
from apps.rpg.catalog_support import (
    available_pet_variants, egg_species, item_is_available, item_unavailable_reason,
    pet_is_available, potion_is_available, potion_type_for_item,
)
from apps.rpg.constants import TriggerType
from apps.rpg.content.validation import validate_badge_criteria
from apps.rpg.models import DropTable, ItemDefinition
from apps.rpg.item_effects import effect_summary

from .shapes import to_plain


def catalog_queryset(section):
    """Only global definitions; custom parent quests never enter this surface."""
    return {
        "categories": lambda: SkillCategory.objects.all(),
        "subjects": lambda: Subject.objects.all(),
        "skills": lambda: Skill.objects.select_related("subject").prefetch_related("prerequisites"),
        "badges": lambda: Badge.objects.select_related("subject"),
        "quests": lambda: QuestDefinition.objects.filter(is_system=True).select_related("required_badge").prefetch_related(
            "reward_items__item__pet_species", "reward_items__item__potion_type", "skill_tags__skill",
        ),
        "items": lambda: ItemDefinition.objects.select_related("pet_species", "potion_type", "food_species"),
        "drops": lambda: DropTable.objects.select_related("item__pet_species", "item__potion_type"),
        "pet_species": lambda: PetSpecies.objects.prefetch_related("available_potions"),
        "potion_types": lambda: PotionType.objects.all(),
    }[section]()


def catalog_page(params):
    queryset = catalog_queryset(params.section)
    total = queryset.count()
    rows = list(queryset.filter(pk__gt=params.after).order_by("pk")[:params.limit + 1])
    more = len(rows) > params.limit
    selected = rows[:params.limit]
    return selected, {"section": params.section, "total": total, "after": params.after,
                      "next_after": selected[-1].pk if more else None}


def _badge_available(badge):
    try:
        validate_badge_criteria(badge.criteria_type, badge.criteria_value)
        return badge_goal_is_available(badge)
    except (ValidationError, AttributeError, TypeError, ValueError):
        # Invalid authored criteria belong in the audit, not a failed listing.
        return False


def _item_availability(item):
    return {"runtime_available": item_is_available(item), "unavailable_reason": item_unavailable_reason(item)}


def catalog_row(section, row):
    common = {"id": row.pk}
    if section == "categories":
        return {**common, **{key: getattr(row, key) for key in ("name", "icon", "color", "description")}}
    if section == "subjects":
        return {**common, **{key: getattr(row, key) for key in ("name", "category_id", "description", "icon", "order")}}
    if section == "skills":
        return {**common, **{key: getattr(row, key) for key in (
            "name", "category_id", "subject_id", "description", "icon", "order", "level_names", "is_locked_by_default",
        )}, "prerequisites": [{"required_skill_id": link.required_skill_id, "required_level": link.required_level}
                                for link in row.prerequisites.all()]}
    if section == "badges":
        return {**common, **{key: getattr(row, key) for key in (
            "name", "description", "icon", "subject_id", "criteria_type", "criteria_value", "rarity", "xp_bonus", "award_coins",
        )}, "available_for_new_user": _badge_available(row)}
    if section == "items":
        return {**common, **{key: getattr(row, key) for key in (
            "slug", "name", "description", "icon", "sprite_key", "item_type", "rarity", "coin_value", "metadata",
            "pet_species_id", "potion_type_id", "food_species_id",
        )}, "effect_summary": effect_summary(row), **_item_availability(row)}
    if section == "quests":
        return {**common, **{key: getattr(row, key) for key in (
            "name", "description", "icon", "sprite_key", "quest_type", "target_value", "duration_days", "trigger_filter",
            "coin_reward", "xp_reward", "is_repeatable", "is_system", "is_cooperative",
        )}, "required_badge": row.required_badge_id,
                "required_badge_name": row.required_badge.name if row.required_badge_id else None,
                "superseded_by": row.superseded_by_id,
                "available_for_new_user": active_system_definitions().filter(pk=row.pk).exists()
                    and (not row.required_badge_id or _badge_available(row.required_badge)),
                "skill_tags": [{"skill_id": tag.skill_id, "skill_name": tag.skill.name, "xp_weight": tag.xp_weight}
                               for tag in row.skill_tags.all()],
                "reward_items": [{"item_id": reward.item_id, "slug": reward.item.slug, "name": reward.item.name,
                                  "quantity": reward.quantity, **_item_availability(reward.item)}
                                 for reward in row.reward_items.all()]}
    if section == "drops":
        return {**common, "trigger_type": row.trigger_type, "item_id": row.item_id,
                "item_slug": row.item.slug, "weight": row.weight, "min_level": row.min_level,
                **_item_availability(row.item)}
    if section == "pet_species":
        return {**common, **{key: getattr(row, key) for key in (
            "slug", "name", "description", "icon", "sprite_key", "food_preference",
        )}, "runtime_available": pet_is_available(row),
                "available_potion_ids": [potion.pk for potion in row.available_potions.all()],
                "supported_potion_ids": list(available_pet_variants(row).values_list("pk", flat=True))}
    return {**common, **{key: getattr(row, key) for key in (
        "slug", "name", "description", "sprite_key", "color_hex", "rarity",
    )}, "runtime_available": potion_is_available(row)}


def _finding(code, section, row, detail, severity="warning"):
    return {"code": code, "section": section, "id": row.pk, "detail": detail, "severity": severity}


def _skill_cycle_ids(skills):
    """Inspect at most 5,000 prerequisite edges, without player progress reads."""
    links = list(SkillPrerequisite.objects.order_by("pk").values_list("skill_id", "required_skill_id")[:5001])
    truncated = len(links) > 5000
    graph = {}
    for source, target in links[:5000]:
        graph.setdefault(source, set()).add(target)
    cyclic = set()
    # Per-start iterative traversal avoids Python recursion and path explosion.
    for start in skills:
        pending, seen = list(graph.get(start, ())), set()
        while pending:
            node = pending.pop()
            if node == start:
                cyclic.add(start)
                break
            if node not in seen:
                seen.add(node)
                pending.extend(graph.get(node, ()))
    return cyclic, truncated


def audit_catalog_rows(section, rows):
    from apps.rpg.services import ConsumableService

    findings = []
    cycle_ids, incomplete = _skill_cycle_ids([row.pk for row in rows]) if section == "skills" else (set(), False)
    for row in rows:
        if section == "items":
            if row.item_type not in ItemDefinition.ItemType.values:
                findings.append(_finding("unknown_item_type", section, row, "Item type has no declared runtime contract.", "error"))
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            effect = metadata.get("effect")
            if row.item_type == "consumable" and (not isinstance(effect, str) or effect not in ConsumableService.SUPPORTED_EFFECTS):
                findings.append(_finding("unknown_consumable_effect", section, row, "Consumable effect has no registered runtime handler.", "error"))
            if row.item_type == "egg" and egg_species(row) is None:
                findings.append(_finding("orphan_reference", section, row, "Egg has no valid typed or legacy species binding.", "error"))
            if row.item_type == "potion" and potion_type_for_item(row) is None:
                findings.append(_finding("orphan_reference", section, row, "Potion has no valid typed or legacy variant binding.", "error"))
            if not item_is_available(row):
                findings.append(_finding("unsupported_item", section, row, item_unavailable_reason(row), "info"))
        elif section == "quests":
            if row.superseded_by_id:
                findings.append(_finding("superseded_quest_definition", section, row,
                    f"Retained history alias of definition {row.superseded_by_id}; no new offers or repeat windows.", "info"))
            elif QuestDefinition.objects.filter(
                is_system=True, name=row.name, superseded_by__isnull=True,
            ).exclude(pk=row.pk).exists():
                findings.append(_finding("ambiguous_system_quest", section, row,
                    "Multiple unreconciled system definitions share this name; new offers and starts are held.", "error"))
            try:
                validate_trigger_filter(row.trigger_filter)
            except (ValidationError, TypeError, ValueError) as exc:
                detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Malformed trigger filter."
                findings.append(_finding("invalid_trigger_filter", section, row, detail, "error"))
            if row.required_badge_id and not _badge_available(row.required_badge):
                findings.append(_finding("unreachable_required_badge", section, row,
                    "Required badge is unreachable through new supported acquisition; saved earned badges may still qualify."))
            if row.xp_reward and not any(tag.xp_weight > 0 for tag in row.skill_tags.all()):
                findings.append(_finding("xp_without_skill_targets", section, row, "Quest promises XP without positive skill weights.", "error"))
            for reward in row.reward_items.all():
                if not item_is_available(reward.item):
                    findings.append(_finding("unsupported_reward_item", section, row,
                        f"New acceptance excludes item {reward.item.slug or reward.item_id}; frozen existing promises are unaffected."))
            filters = row.trigger_filter if isinstance(row.trigger_filter, dict) else {}
            category = filters.get("skill_category_id")
            if category and (type(category) is not int or not SkillCategory.objects.filter(pk=category).exists()):
                findings.append(_finding("orphan_reference", section, row, "Trigger filter names a missing skill category.", "error"))
            if any(filters.get(key) for key in ("project_id", "chore_ids", "savings_goal_id")):
                findings.append(_finding("family_specific_filter", section, row,
                    "Global quest contains a family-object filter; this global audit does not inspect private referenced records."))
        elif section == "badges":
            try:
                validate_badge_criteria(row.criteria_type, row.criteria_value)
            except (ValidationError, TypeError, ValueError) as exc:
                detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Malformed badge criteria."
                findings.append(_finding("invalid_badge_criteria", section, row, detail, "error"))
            if not _badge_available(row):
                findings.append(_finding("unreachable_badge", section, row,
                    "Goal is unreachable through new supported acquisition; saved ownership or an earned badge may still qualify."))
            criteria = row.criteria_value if isinstance(row.criteria_value, dict) else {}
            if row.criteria_type == "cosmetic_set_owned":
                slugs = criteria.get("slugs")
                if isinstance(slugs, list) and all(isinstance(slug, str) for slug in slugs):
                    if ItemDefinition.objects.filter(slug__in=slugs).count() != len(set(slugs)):
                        findings.append(_finding("orphan_reference", section, row, "Named cosmetic set contains an absent item.", "error"))
            elif row.criteria_type == "quest_completed":
                names = criteria.get("quest_names") or ([criteria["quest_name"]] if criteria.get("quest_name") else [])
                if isinstance(names, list) and all(isinstance(name, str) for name in names):
                    # Parent-authored private definitions cannot make a global catalog goal reachable.
                    if active_system_definitions().filter(name__in=names).values("name").distinct().count() != len(set(names)):
                        findings.append(_finding("orphan_reference", section, row, "Badge names a quest absent from the global system catalog."))
        elif section == "skills":
            if row.pk in cycle_ids:
                findings.append(_finding("skill_cycle", section, row, "Prerequisites contain a cycle through this skill.", "error"))
            if row.subject_id and row.subject.category_id != row.category_id:
                findings.append(_finding("taxonomy_mismatch", section, row, "Skill and subject belong to different categories.", "error"))
            for prerequisite in row.prerequisites.all():
                if prerequisite.required_level not in XP_THRESHOLDS:
                    findings.append(_finding("unreachable_skill_level", section, row,
                        "A prerequisite requests a level outside the runtime XP curve.", "error"))
        elif section == "drops":
            if row.trigger_type not in TriggerType.values:
                findings.append(_finding("invalid_trigger_filter", section, row, "Drop trigger is not in the runtime trigger vocabulary.", "error"))
            if not item_is_available(row.item):
                findings.append(_finding("unsupported_reward_item", section, row, "Drop item is excluded by the acquisition policy."))
            if not row.weight:
                findings.append(_finding("zero_drop_weight", section, row, "A zero-weight drop entry cannot be selected."))
    return to_plain(findings), incomplete
