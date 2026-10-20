"""Domain checks shared by content preview and actual loading."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.quests.validators import validate_trigger_filter

# Keep keys explicit: accepting a misspelling can silently change reward eligibility.
CRITERIA_KEYS = {
    "hours_worked": {"hours"}, "hours_in_day": {"hours"}, "streak_days": {"days"},
    "category_projects": {"categories", "category", "count"},
    "skill_level_reached": {"count", "level"}, "subjects_completed": {"count", "min_level"},
    "skill_categories_breadth": {"categories", "min_level"},
    "homework_planned_ahead": {"count", "days_ahead"},
    "quest_completed": {"count", "quest_name", "quest_names"},
    "habit_max_strength": {"strength"}, "early_bird": {"hour"}, "late_night": {"hour"},
    "fast_project": {"days"}, "category_mastery": {"category", "min_level"},
    "grade_reached": {"grade"}, "habit_count_at_strength": {"count", "strength"},
    "journal_streak_days": {"days"}, "movement_total_minutes": {"minutes"},
    "cosmetic_set_owned": {"slugs"},
}
COUNT_CRITERIA = set("days_worked projects_completed skills_unlocked photos_uploaded homework_on_time_count pets_hatched pet_species_owned mounts_evolved chore_completions milestones_completed savings_goal_completed bounty_completed reward_redeemed perfect_days_count streak_freeze_used consumable_variety birthdays_logged habit_taps_lifetime badges_earned_count co_op_project_completed boss_quests_completed collection_quests_completed chronicle_milestones_logged journal_entries_written creations_logged creations_approved creation_skill_breadth movement_sessions_logged movement_type_breadth".split())
for _name in COUNT_CRITERIA:
    CRITERIA_KEYS[_name] = {"count"}
for _name in ("total_earned", "total_coins_earned", "coins_spent_lifetime"):
    CRITERIA_KEYS[_name] = {"amount"}


ENTRY_FIELDS = {
    "categories": set("id name icon color description".split()),
    "subjects": set("id name category icon order description".split()),
    "skills": set("id name category subject icon levels locked order description prereqs".split()),
    "badges": set("id name description icon criteria_type criteria_value xp_bonus rarity award_coins".split()),
    "potions": set("id slug name sprite_key color_hex rarity description item_name item_icon coin_value".split()),
    "species": set("id slug name icon sprite_key description food_preference available_potions egg_name egg_icon egg_sprite_key egg_rarity egg_coin_value".split()),
    "items": set("id slug name icon sprite_key item_type rarity coin_value metadata description food_species".split()),
    "rules": set("id trigger triggers item_slugs weight min_level".split()),
    "macros": set("id triggers item_type item_type_startswith weight_by_rarity weight min_level".split()),
    "quests": set("id name description icon sprite_key quest_type target_value duration_days trigger_filter coin_reward xp_reward is_repeatable is_system is_cooperative required_badge reward_items skill_tags prerequisite_quest required_skill required_skill_level".split()),
    "rewards": set("id name description icon cost_coins rarity stock requires_parent_approval is_active order fulfillment_kind item_definition".split()),
}
SECTION_KEYS = {"skill_tree": {"categories", "subjects", "skills"}, "badges": {"badges"},
                "potion_types": {"potions"}, "pet_species": {"species"}, "items": {"items"},
                "drops": {"rules", "macros"}, "quests": {"quests"}, "rewards": {"rewards"}}


def bounded_number(value, label, minimum=0, maximum=1000000):
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a number.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f"{label} must be a finite number.") from None
    if not number.is_finite() or number < minimum or number > maximum:
        raise ValidationError(f"{label} must be between {minimum} and {maximum}.")
    return number


def whole_number(value, label, minimum=0, maximum=1000000):
    number = bounded_number(value, label, minimum, maximum)
    if number != number.to_integral_value():
        raise ValidationError(f"{label} must be a whole number.")
    return number


def validate_badge_criteria(criteria_type, value):
    from apps.achievements.models import Badge
    if criteria_type not in Badge.CriteriaType.values:
        raise ValidationError("Unknown badge criteria_type.")
    if not isinstance(value, dict):
        raise ValidationError("criteria_value must be an object.")
    unknown = set(value) - CRITERIA_KEYS.get(criteria_type, set())
    if unknown:
        raise ValidationError(f"Unknown criteria_value keys: {sorted(unknown)}.")
    for key, item in value.items():
        if key in {"category", "quest_name"}:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError(f"criteria_value.{key} must be nonempty text.")
        elif key in {"slugs", "quest_names"}:
            if not isinstance(item, list) or not item or not all(isinstance(s, str) and s.strip() for s in item):
                raise ValidationError(f"criteria_value.{key} must be a nonempty list of names.")
        else:
            # Validating a coerced Decimal without changing the saved JSON
            # leaves strings such as "2" to crash numeric runtime checkers.
            # Accept actual JSON numbers only, consistently for every writer.
            if type(item) not in {int, float}:
                raise ValidationError(f"criteria_value.{key} must be a number.")
            maximum = 23 if key == "hour" else 12 if key == "grade" else 1000000
            minimum = 0 if key in {"hour", "grade", "days_ahead"} else 1
            number = bounded_number(item, f"criteria_value.{key}", minimum, maximum)
            if key != "amount" and number != number.to_integral_value():
                raise ValidationError(f"criteria_value.{key} must be a whole number.")


def validate_content(parsed, *, strict=True):
    """Reject malformed eligibility and reward rules before any upsert."""
    from apps.rpg.content.loader import ContentPackError
    from apps.achievements.models import Badge
    try:
        for section, data in parsed.items():
            if strict and set(data) - SECTION_KEYS[section]:
                raise ValidationError(f"Unknown {section} fields: {sorted(set(data) - SECTION_KEYS[section])}.")
            for key, rows in data.items():
                if not isinstance(rows, list):
                    raise ValidationError(f"{section}.{key} must be a list.")
                identities = set()
                for entry in rows:
                    if not isinstance(entry, dict):
                        raise ValidationError(f"{section}.{key} entries must be objects.")
                    identity = entry.get("id") or entry.get("slug") or entry.get("name")
                    if strict and identity is not None:
                        if not isinstance(identity, str) or identity in identities:
                            raise ValidationError(f"Duplicate or invalid {key} entry identity.")
                        identities.add(identity)
                    if strict and set(entry) - ENTRY_FIELDS[key]:
                        raise ValidationError(f"Unknown {key} entry fields: {sorted(set(entry) - ENTRY_FIELDS[key])}.")
                    if "id" in entry and (not isinstance(entry["id"], str) or not entry["id"] or len(entry["id"]) > 150):
                        raise ValidationError("Entry id must be nonempty text of at most 150 characters.")
                    for field in ("coin_reward", "xp_reward", "xp_bonus", "coin_value", "egg_coin_value", "cost_coins", "stock", "min_level", "order"):
                        if field in entry and entry[field] is not None:
                            number = bounded_number(entry[field], field)
                            if number != number.to_integral_value():
                                raise ValidationError(f"{field} must be a whole number.")
                    for field in ("is_active", "is_repeatable", "is_system", "is_cooperative", "requires_parent_approval", "award_coins", "locked"):
                        if field in entry and type(entry[field]) is not bool:
                            raise ValidationError(f"{field} must be a boolean.")
                    if "weight_by_rarity" in entry:
                        weights = entry["weight_by_rarity"]
                        if not isinstance(weights, dict) or set(weights) - set(Badge.Rarity.values):
                            raise ValidationError("weight_by_rarity must map known rarities to positive weights.")
                        for weight in weights.values():
                            whole_number(weight, "rarity weight", 1)
                    if "rarity" in entry and entry["rarity"] not in Badge.Rarity.values:
                        raise ValidationError("Unknown rarity.")
                    for field, maximum in (("target_value", 1000000), ("duration_days", 365), ("weight", 1000000)):
                        if field in entry:
                            number = bounded_number(entry[field], field, 1, maximum)
                            if number != number.to_integral_value():
                                raise ValidationError(f"{field} must be a whole number.")
                    if section == "quests":
                        if strict and entry.get("is_system") is False:
                            raise ValidationError("Content packs publish global catalog quests; use family goal authoring for private challenges.")
                        if entry.get("quest_type") not in {"boss", "collection"}:
                            raise ValidationError("Unknown quest_type.")
                        filters = entry.get("trigger_filter", {})
                        validate_trigger_filter(filters)
                        for filter_key in ("project_id", "skill_category_id", "savings_goal_id"):
                            if filter_key in filters and (type(filters[filter_key]) is not int or filters[filter_key] < 1):
                                raise ValidationError(f"trigger_filter.{filter_key} must be a positive integer.")
                        if "chore_ids" in filters and (not isinstance(filters["chore_ids"], list) or not all(type(i) is int and i > 0 for i in filters["chore_ids"])):
                            raise ValidationError("trigger_filter.chore_ids must be a list of positive integers.")
                        if "on_time" in filters and type(filters["on_time"]) is not bool:
                            raise ValidationError("trigger_filter.on_time must be a boolean.")
                        for reference in ("prerequisite_quest", "required_skill"):
                            if entry.get(reference) is not None and (not isinstance(entry[reference], str) or not entry[reference].strip()):
                                raise ValidationError(f"{reference} must be a nonempty global name or null.")
                        level = entry.get("required_skill_level", 0)
                        if type(level) is not int or not 0 <= level <= 6 or bool(entry.get("required_skill")) != bool(level):
                            raise ValidationError("required_skill needs a whole level from 1 to 6; without a skill use level 0.")
                        for reward in entry.get("reward_items", []):
                            whole_number(reward.get("quantity", 1), "reward quantity", 1, 10000)
                        for tag in entry.get("skill_tags", []):
                            if isinstance(tag, dict):
                                whole_number(tag.get("weight", 1), "skill weight", 1, 5)
                    if section == "skill_tree" and key == "skills":
                        for prerequisite in entry.get("prereqs", []):
                            if isinstance(prerequisite, dict):
                                whole_number(prerequisite.get("level", 2), "prerequisite level", 0, 100)
                    if section == "badges" and strict:
                        validate_badge_criteria(entry.get("criteria_type"), entry.get("criteria_value", {}))
    except (ValidationError, TypeError, KeyError, AttributeError) as error:
        messages = getattr(error, "messages", [str(error)])
        raise ContentPackError("; ".join(messages)) from error
