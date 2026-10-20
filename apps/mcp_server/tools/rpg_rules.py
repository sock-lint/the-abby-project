"""Inspect installed mechanics and global dependencies without player state."""
from copy import deepcopy

from apps.achievements.models import Badge, Skill, SkillPrerequisite
from apps.pets.expeditions import TIER_CONFIG
from apps.pets.services import COMPANION_DAILY_GROWTH, EVOLUTION_THRESHOLD, PetService
from apps.quests.models import QuestDefinition
from apps.rpg.content.publication import _digest
from apps.rpg.content.validation import CRITERIA_KEYS
from apps.rpg.item_effects import FOOD_GROWTH_BY_RARITY, MAX_AUTHORED_FOOD_GROWTH, PREFERRED_FOOD_BONUS
from apps.rpg.models import DropTable
from apps.rpg.services import ConsumableService

from ..catalog import audit_catalog_rows, catalog_queryset, catalog_row
from ..context import get_current_user
from ..economy import economy_rules
from ..errors import MCPNotFoundError, safe_tool
from ..rpg_rule_schemas import CatalogExplanationResult, ExplainCatalogEntryIn, GetRpgRulesIn, RpgRulesResult
from ..server import tool
from ..shapes import to_plain


@tool()
@safe_tool
def get_rpg_rules(params: GetRpgRulesIn) -> RpgRulesResult:
    """Read installed mechanics and the boundary between content and code edits.

    This manifest grants no ability to set XP curves, timers, art support or
    execute code. Catalog definitions and existing effect parameters are authored
    through reviewed drafts/packs; new mechanics require reviewed source changes.
    """
    get_current_user()
    rules = {"schema_version": 1, "economy": economy_rules(),
        "food_growth": {"rarity_floor": dict(FOOD_GROWTH_BY_RARITY), "preferred_bonus": PREFERRED_FOOD_BONUS,
                        "maximum_authored_growth": MAX_AUTHORED_FOOD_GROWTH},
        "companions": {"incubation_seconds": PetService.incubation_duration_seconds(),
                       "evolution_growth": EVOLUTION_THRESHOLD, "daily_growth": COMPANION_DAILY_GROWTH},
        "expeditions": deepcopy(TIER_CONFIG), "consumable_effects": sorted(ConsumableService.SUPPORTED_EFFECTS),
        "badge_criteria": {value: sorted(CRITERIA_KEYS.get(value, ())) for value in Badge.CriteriaType.values},
        "authoring": {
            "definitions": ["skills", "badges", "quests", "items", "drop weights", "species and compatible potion definitions"],
            "installed_mechanics": ["XP thresholds", "rarity budgets", "expedition tier rules", "incubation duration", "new consumable effect handlers", "asset support policy"],
            "editorial": ["existing Lorebook copy", "affirmation copy and future selection"],
        }}
    return {**rules, "fingerprint": _digest(rules)}


@tool()
@safe_tool
def explain_rpg_catalog_entry(params: ExplainCatalogEntryIn) -> CatalogExplanationResult:
    """Explain a global definition's effective rules, audit and incoming links.

    References are bounded global definitions only. Family shops, parent goals,
    inventory and saved progress require separate household access and are omitted.
    """
    get_current_user()
    row = catalog_queryset(params.section).filter(pk=params.object_id).first()
    if row is None:
        raise MCPNotFoundError("Global catalog entry not found.")
    findings, _ = audit_catalog_rows(params.section, [row])
    references = []
    if params.section == "items":
        references.extend({"section": "quests", "id": q.pk, "name": q.name} for q in QuestDefinition.objects.filter(
            is_system=True, reward_items__item_id=row.pk).distinct().order_by("pk")[:params.limit + 1])
        references.extend({"section": "drops", "id": d.pk, "trigger_type": d.trigger_type} for d in DropTable.objects.filter(
            item_id=row.pk).order_by("pk")[:params.limit + 1])
    elif params.section == "skills":
        references.extend({"section": "skills", "id": link.skill_id} for link in SkillPrerequisite.objects.filter(
            required_skill_id=row.pk).order_by("pk")[:params.limit + 1])
        references.extend({"section": "quests", "id": q.pk, "name": q.name} for q in QuestDefinition.objects.filter(
            is_system=True, skill_tags__skill_id=row.pk).distinct().order_by("pk")[:params.limit + 1])
    elif params.section == "badges":
        references.extend({"section": "quests", "id": q.pk, "name": q.name} for q in QuestDefinition.objects.filter(
            is_system=True, required_badge_id=row.pk).order_by("pk")[:params.limit + 1])
    elif params.section in {"categories", "subjects"}:
        references.extend({"section": "skills", "id": skill.pk, "name": skill.name} for skill in Skill.objects.filter(
            **{"category_id" if params.section == "categories" else "subject_id": row.pk}).order_by("pk")[:params.limit + 1])
    return to_plain({"section": params.section, "entry": catalog_row(params.section, row), "findings": findings,
        "references": references[:params.limit], "references_truncated": len(references) > params.limit,
        "scope": "global_definitions_only"})
