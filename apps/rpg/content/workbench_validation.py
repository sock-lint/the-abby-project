"""Strict, bounded editor inputs with exact global references."""
import json
import re

from django.core.exceptions import ValidationError

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.quests.validators import validate_trigger_filter
from apps.rpg.models import ContentPackEntry, ItemDefinition, RPGContentOverride
from apps.rpg.services import ConsumableService

from .loader import ContentPackError
from .validation import whole_number

ITEM_FIELDS = {"name", "description", "icon", "sprite_key", "rarity", "coin_value", "metadata"}
ITEM_BEHAVIOR_FIELDS = {"rarity", "coin_value", "metadata"}
NEW_ITEM_FIELDS = ITEM_FIELDS | {"slug", "item_type", "food_species_id"}
QUEST_FIELDS = {"name", "description", "icon", "sprite_key", "quest_type", "target_value", "duration_days",
                "trigger_filter", "coin_reward", "xp_reward", "is_repeatable", "is_cooperative", "required_badge", "reward_items", "skill_tags",
                "prerequisite_quest", "required_skill", "required_skill_level"}
CREATE_ITEM_TYPES = set(ItemDefinition.ItemType.values) - {"egg", "potion"}
MODELS = {"items": ItemDefinition, "quests": QuestDefinition}


def supported_challenge_triggers(quest_type="collection"):
    from apps.quests.goals import FACT_TRIGGERS
    from apps.quests.services import TRIGGER_DAMAGE
    return sorted(trigger for trigger in FACT_TRIGGERS
                  if quest_type != "boss" or TRIGGER_DAMAGE.get(trigger, 0) > 0)


def challenge_trigger_status(quest_type, filters):
    """Explain actual automatic tracking independently of legacy trigger names."""
    from apps.quests.goals import EFFORT_TRIGGERS
    supported = set(supported_challenge_triggers(quest_type))
    if not isinstance(filters, dict):
        return {"available": False, "unsupported": []}
    allowed = filters.get("allowed_triggers")
    if allowed is not None and (not isinstance(allowed, list) or any(not isinstance(trigger, str) for trigger in allowed)):
        return {"available": False, "unsupported": []}
    effective = set(allowed or EFFORT_TRIGGERS)
    return {"available": bool(effective & supported), "unsupported": sorted(set(allowed or ()) - supported)}


def challenge_trigger_findings(rows):
    findings = []
    for row in rows:
        status = challenge_trigger_status(row.quest_type, row.trigger_filter)
        if status["unsupported"]:
            findings.append({"code": "unsupported_challenge_trigger", "section": "quests", "id": row.pk,
                "severity": "warning", "detail": "These activities cannot advance this automatic challenge: "
                + ", ".join(status["unsupported"]) + ". Choose supported activities before republishing."})
    return findings


def require_actor(actor):
    if actor.role != "parent" or not actor.is_staff or not actor.is_active or actor.family_id is None:
        raise ContentPackError("Content authoring requires an active staff parent with an explicit family.")


def editable_object(actor, section, object_id):
    model = MODELS[section]
    obj = model.objects.filter(pk=object_id).first()
    if obj is None or (section == "quests" and not obj.is_system):
        raise ContentPackError("The selected global catalog object was not found.")
    claim = ContentPackEntry.objects.filter(model_label=model._meta.label_lower, object_id=obj.pk).first()
    override = RPGContentOverride.objects.filter(model_label=model._meta.label_lower, object_id=obj.pk).first()
    if ((claim and claim.family_id != actor.family_id)
            or (override and override.family_id != actor.family_id)):
        raise ContentPackError("This catalog entry is authored by another family and is read-only here.")
    return obj


def _text(value, field, maximum, *, empty=True):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ContentPackError(f"{field} must be {'nonempty ' if not empty else ''}text of at most {maximum} characters.")


def _positive_id(value, field):
    if type(value) is not int or value < 1:
        raise ContentPackError(f"{field} must be a positive integer.")


def _validate_values(section, values, *, new):
    allowed = (NEW_ITEM_FIELDS if new else ITEM_FIELDS) if section == "items" else QUEST_FIELDS
    if not isinstance(values, dict) or set(values) - allowed:
        raise ContentPackError(f"Unknown editable {section} fields: {sorted(set(values) - allowed) if isinstance(values, dict) else 'supply an object'}.")
    for field, maximum in (("name", 100), ("description", 10000), ("icon", 50), ("sprite_key", 64), ("slug", 100)):
        if field in values:
            _text(values[field], field, maximum, empty=field not in {"name", "slug"})
    for field in ("coin_value", "coin_reward", "xp_reward", "target_value", "duration_days"):
        if field in values:
            minimum = 1 if field in {"target_value", "duration_days"} else 0
            maximum = 365 if field == "duration_days" else 1000000
            # JSON strings are not numbers in the browser's editor contract.
            if type(values[field]) is not int:
                raise ContentPackError(f"{field} must be a whole number.")
            whole_number(values[field], field, minimum, maximum)
    if "rarity" in values and values["rarity"] not in ItemDefinition.Rarity.values:
        raise ContentPackError("Unknown rarity.")
    for field in ("is_repeatable", "is_cooperative"):
        if field in values and type(values[field]) is not bool:
            raise ContentPackError(f"{field} must be a boolean.")
    if "quest_type" in values and values["quest_type"] not in QuestDefinition.QuestType.values:
        raise ContentPackError("Unknown quest_type.")
    if section == "items":
        if "metadata" in values and (not isinstance(values["metadata"], dict) or len(json.dumps(values["metadata"])) > 10000):
            raise ContentPackError("metadata must be an object of at most 10 KB.")
        if "item_type" in values and (not isinstance(values["item_type"], str) or values["item_type"] not in CREATE_ITEM_TYPES):
            raise ContentPackError("Create eggs and hatching potions through their species/potion authoring workflow.")
        if new:
            missing = {"name", "slug", "item_type"} - values.keys()
            if missing:
                raise ContentPackError(f"New items require {', '.join(sorted(missing))}.")
        if values.get("food_species_id") is not None:
            from apps.pets.models import PetSpecies
            _positive_id(values["food_species_id"], "food_species_id")
            if not PetSpecies.objects.filter(pk=values["food_species_id"]).exists():
                raise ContentPackError("Unknown food species.")
        return
    if new and {"name", "quest_type", "target_value"} - values.keys():
        raise ContentPackError("New challenges require name, quest_type and target_value.")
    if "trigger_filter" in values:
        filters = values["trigger_filter"]
        if not isinstance(filters, dict):
            raise ContentPackError("trigger_filter must be an object.")
        if "allowed_triggers" in filters and (not isinstance(filters["allowed_triggers"], list)
                or any(not isinstance(trigger, str) for trigger in filters["allowed_triggers"])):
            raise ContentPackError("trigger_filter.allowed_triggers must be a list of trigger strings.")
        validate_trigger_filter(filters)
        if any(key in filters for key in ("project_id", "chore_ids", "savings_goal_id")):
            raise ContentPackError("Global catalog challenges cannot reference private family objects.")
        if "on_time" in filters and type(filters["on_time"]) is not bool:
            raise ContentPackError("trigger_filter.on_time must be a boolean.")
        if "skill_category_id" in filters:
            _positive_id(filters["skill_category_id"], "skill_category_id")
            if not SkillCategory.objects.filter(pk=filters["skill_category_id"]).exists():
                raise ContentPackError("Unknown skill category.")
    if values.get("required_badge") is not None:
        _positive_id(values["required_badge"], "required_badge")
        if not Badge.objects.filter(pk=values["required_badge"]).exists():
            raise ContentPackError("Unknown required badge.")
    for field, model in (("prerequisite_quest", QuestDefinition), ("required_skill", Skill)):
        if values.get(field) is not None:
            _positive_id(values[field], field)
            matches = model.objects.filter(pk=values[field])
            if field == "prerequisite_quest":
                from apps.quests.queries import active_system_definitions
                matches = matches.filter(pk__in=active_system_definitions().values("pk"), created_by=None)
            if not matches.exists():
                raise ContentPackError(f"Unknown global {field}.")
    if "required_skill_level" in values:
        if type(values["required_skill_level"]) is not int:
            raise ContentPackError("required_skill_level must be a whole number.")
        whole_number(values["required_skill_level"], "required_skill_level", 0, 6)
    for field in ("reward_items", "skill_tags"):
        if field not in values:
            continue
        rows = values[field]
        if not isinstance(rows, list) or len(rows) > 50:
            raise ContentPackError(f"{field} must be a list of at most 50 links.")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ContentPackError(f"{field} links must be objects.")
            if field == "reward_items":
                if set(row) - {"item_id", "item_key", "quantity"} or ("item_id" in row) == ("item_key" in row):
                    raise ContentPackError("Each reward must select exactly one item_id or draft item_key.")
                reference = row.get("item_id", row.get("item_key"))
                if "item_id" in row:
                    _positive_id(reference, "item_id")
                    if not ItemDefinition.objects.filter(pk=reference).exists():
                        raise ContentPackError("Unknown reward item.")
                else:
                    _text(reference, "item_key", 64, empty=False)
                quantity = row.get("quantity", 1)
                if type(quantity) is not int:
                    raise ContentPackError("Reward quantity must be a whole number.")
                whole_number(quantity, "Reward quantity", 1, 10000)
                identity = ("id" if "item_id" in row else "key", reference)
            else:
                if set(row) - {"skill_id", "xp_weight"} or "skill_id" not in row:
                    raise ContentPackError("Skill tags require an exact skill_id and xp_weight.")
                _positive_id(row["skill_id"], "skill_id")
                if not Skill.objects.filter(pk=row["skill_id"]).exists():
                    raise ContentPackError("Unknown skill.")
                weight = row.get("xp_weight", 1)
                if type(weight) is not int:
                    raise ContentPackError("Skill weight must be a whole number.")
                whole_number(weight, "Skill weight", 1, 5)
                identity = row["skill_id"]
            if identity in seen:
                raise ContentPackError(f"Duplicate {field} reference.")
            seen.add(identity)


def _validate_taxonomy_choices(values, current, *, lock):
    from apps.achievements.taxonomy import validate_new_taxonomy_references

    if "required_skill" in values and values["required_skill"] is not None:
        validate_new_taxonomy_references(Skill, [values["required_skill"]],
            retained_ids=[current.required_skill_id] if current else (), lock=lock)
    if "trigger_filter" in values:
        category_id = values["trigger_filter"].get("skill_category_id")
        if category_id is not None:
            prior = current.trigger_filter.get("skill_category_id") if current else None
            validate_new_taxonomy_references(SkillCategory, [category_id], retained_ids=[prior], lock=lock)
    if "skill_tags" in values:
        validate_new_taxonomy_references(Skill, [row["skill_id"] for row in values["skill_tags"]],
            retained_ids=current.skill_tags.values_list("skill_id", flat=True) if current else (), lock=lock)


def validate_changes(actor, changes, *, lock=False):
    """Validate replacement draft entries without applying catalog mutations."""
    require_actor(actor)
    try:
        encoded = json.dumps(changes, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise ContentPackError("Draft content must be finite JSON values.") from error
    if not isinstance(changes, list) or len(changes) > 100 or len(encoded) > 200000:
        raise ContentPackError("A draft contains at most 100 changes and 200 KB of content.")
    seen, objects, new_items = set(), set(), set()
    try:
        for change in changes:
            if not isinstance(change, dict) or set(change) != {"section", "object_id", "key", "values"}:
                raise ContentPackError("Changes require exactly section, object_id, key and values.")
            section, object_id, key = change["section"], change["object_id"], change["key"]
            if not isinstance(section, str) or section not in MODELS:
                raise ContentPackError("Only challenge and item definitions are editable here.")
            if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", key):
                raise ContentPackError("A stable key uses 1–64 lowercase letters, digits or hyphens.")
            if (section, key) in seen:
                raise ContentPackError("Draft keys must be unique within each section.")
            seen.add((section, key))
            if object_id is not None:
                _positive_id(object_id, "object_id")
                if (section, object_id) in objects:
                    raise ContentPackError("Each catalog object can occur only once in a draft.")
                objects.add((section, object_id))
                obj = editable_object(actor, section, object_id)
                if section == "items" and isinstance(change["values"], dict):
                    for field in ITEM_BEHAVIOR_FIELDS:
                        if field in change["values"] and change["values"][field] != getattr(obj, field):
                            raise ContentPackError(f"Existing item {field} preserves earned inventory and promises; create a new item version to change its behavior.")
                if (section == "items" and obj.item_type in {"egg", "potion"}
                        and isinstance(change["values"], dict) and "metadata" in change["values"]):
                    if change["values"]["metadata"] != obj.metadata:
                        raise ContentPackError("Generated egg/potion bindings are edited through species/potion authoring.")
            elif section == "items":
                new_items.add(key)
            _validate_values(section, change["values"], new=object_id is None)
            if section == "quests":
                _validate_taxonomy_choices(change["values"], obj if object_id else None, lock=lock)
                quest_type = change["values"].get("quest_type", obj.quest_type if object_id else "collection")
                filters = change["values"].get("trigger_filter", obj.trigger_filter if object_id else {})
                status = challenge_trigger_status(quest_type, filters)
                if status["unsupported"]:
                    raise ContentPackError("These activities cannot advance this automatic challenge: "
                        + ", ".join(status["unsupported"]) + ". Choose supported activities.")
                if not status["available"]:
                    raise ContentPackError("Choose valid supported activities for this automatic challenge.")
        for change in changes:
            for row in change["values"].get("reward_items", []):
                if "item_key" in row and row["item_key"] not in new_items:
                    raise ContentPackError("Reward item_key must select a new item in this draft.")
        # Validate the proposed graph together: individually safe edits can
        # form a cycle when applied in the same draft.
        from copy import copy
        from .authoring import validate_source_identity
        graph = dict(QuestDefinition.objects.values_list("pk", "prerequisite_quest_id"))
        for change in changes:
            if change["section"] != "quests":
                continue
            obj = copy(editable_object(actor, "quests", change["object_id"])) if change["object_id"] else QuestDefinition(is_system=True)
            for field, value in change["values"].items():
                if field not in {"reward_items", "skill_tags"}:
                    setattr(obj, field + "_id" if field in {"required_badge", "prerequisite_quest", "required_skill"} else field, value)
            validate_source_identity(obj)
            obj.clean()
            if obj.pk:
                graph[obj.pk] = obj.prerequisite_quest_id
        for start in [change["object_id"] for change in changes if change["section"] == "quests" and change["object_id"]]:
            seen, current = set(), start
            while current is not None:
                if current in seen:
                    raise ContentPackError("Challenge prerequisites cannot form a cycle.")
                seen.add(current)
                if len(seen) > 100:
                    raise ContentPackError("Challenge prerequisite chains contain at most 100 entries.")
                current = graph.get(current)
    except ValidationError as error:
        raise ContentPackError("; ".join(error.messages)) from error
    return changes


def validate_item_runtime(item):
    from apps.rpg.item_effects import MAX_AUTHORED_FOOD_GROWTH
    metadata = item.metadata
    if not isinstance(metadata, dict):
        raise ContentPackError("Item metadata must be an object.")
    numeric_limits = {"duration_days": 365, "duration_hours": 8760, "feeds": 100, "growth": 100,
                      "count": 100, "xp": 10000, "coins": 1000000}
    for field, maximum in numeric_limits.items():
        if field not in metadata:
            continue
        maximum = MAX_AUTHORED_FOOD_GROWTH if field == "growth" and item.item_type == "food" else maximum
        if type(metadata[field]) is not int or not 1 <= metadata[field] <= maximum:
            raise ContentPackError(f"metadata.{field} must be a whole number between 1 and {maximum}.")
    if item.item_type == "consumable":
        effect = metadata.get("effect")
        if not isinstance(effect, str) or effect not in ConsumableService.SUPPORTED_EFFECTS:
            raise ContentPackError("Consumables must select an existing runtime effect.")
        if "rarities" in metadata:
            rarities = metadata["rarities"]
            if (not isinstance(rarities, list) or not rarities or len(rarities) > 5
                    or any(not isinstance(rarity, str) or rarity not in ItemDefinition.Rarity.values for rarity in rarities)):
                raise ContentPackError("metadata.rarities must be a nonempty list of known rarities.")
    if item.item_type == "coin_pouch" and not (metadata.get("coins") or item.coin_value):
        raise ContentPackError("A coin pouch needs a positive metadata.coins or coin_value.")
