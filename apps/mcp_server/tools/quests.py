"""Quest MCP tools (Tier 2.2).

New ``QuestDefinition`` rows can be authored two ways:

1. **Via a content pack** (preferred for bundled releases) — ship a
   ``quests.yaml`` in ``content/rpg/packs/<name>/`` and call
   ``load_content_pack``.
2. **Via ``create_quest_definition``** (this module) — for one-off quests
   a parent wants to author outside of any pack. These land with
   ``is_system=False`` and are owned by the creating parent.

Live ``Quest`` instances for a specific child are spawned via
``assign_quest`` (from a QuestDefinition id) or by passing
``assigned_to_id`` to ``create_quest_definition``.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from django.core.exceptions import ValidationError as DjangoValidationError

from django.db import transaction

from apps.achievements.models import Badge
from apps.accounts.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestSkillTag
from apps.quests.services import QuestService
from apps.quests.validators import validate_trigger_filter

from ..context import get_current_user, require_parent
from ..errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
    safe_tool,
)
from ..schemas import (
    AssignCoOpQuestIn,
    AssignQuestIn,
    CancelQuestIn,
    CreateQuestDefinitionIn,
    DeleteQuestDefinitionIn,
    GetQuestIn,
    ListQuestCatalogIn,
    ListQuestsIn,
    SetQuestDefinitionSkillTagsIn,
)
from ..server import tool
from ..shapes import to_plain


# ---------------------------------------------------------------------------
# Serializer helpers
# ---------------------------------------------------------------------------


def _quest_to_dict(quest: Quest) -> dict[str, Any]:
    from apps.quests.serializers import QuestSerializer

    return to_plain(QuestSerializer(quest).data)


def _definition_to_dict(d: QuestDefinition) -> dict[str, Any]:
    from apps.quests.serializers import QuestDefinitionSerializer

    return to_plain(QuestDefinitionSerializer(d).data)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_quests(params: ListQuestsIn) -> dict[str, Any]:
    """List quests visible to the current user.

    Children see only their own participations; parents see all by default
    or filter to a child with ``user_id``.
    """
    user = get_current_user()
    qs = Quest.objects.select_related("definition").prefetch_related(
        "participants",
    )
    if user.role == "parent":
        if params.user_id is not None:
            qs = qs.filter(participants__user_id=params.user_id)
    else:
        qs = qs.filter(participants__user=user)
    if not params.include_completed:
        qs = qs.filter(status=Quest.Status.ACTIVE)
    qs = qs.distinct().order_by("-start_date")[: params.limit]
    return {"quests": [_quest_to_dict(q) for q in qs]}


@tool()
@safe_tool
def get_quest(params: GetQuestIn) -> dict[str, Any]:
    """Get a quest instance with its progress + participants."""
    user = get_current_user()
    try:
        quest = Quest.objects.select_related("definition").get(pk=params.quest_id)
    except Quest.DoesNotExist:
        raise MCPNotFoundError(f"Quest {params.quest_id} not found.")
    if user.role != "parent" and not quest.participants.filter(user=user).exists():
        raise MCPPermissionDenied("This quest is not yours.")
    return _quest_to_dict(quest)


@tool()
@safe_tool
def list_quest_catalog(params: ListQuestCatalogIn) -> dict[str, Any]:
    """Browse every authored QuestDefinition. Parent-only.

    This is the "catalog" the LLM inspects to pick a definition id for
    ``assign_quest``. Filter with ``quest_type`` to narrow to boss or
    collection quests.
    """
    require_parent()
    qs = QuestDefinition.objects.prefetch_related("reward_items__item")
    if params.quest_type:
        qs = qs.filter(quest_type=params.quest_type)
    qs = qs.order_by("quest_type", "name")
    return {"quest_definitions": [_definition_to_dict(d) for d in qs]}


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def create_quest_definition(
    params: CreateQuestDefinitionIn,
) -> dict[str, Any]:
    """Create a custom QuestDefinition (parent-only).

    For system / bundled quests, prefer shipping them in a content pack's
    ``quests.yaml`` — this tool is for one-off quests a parent wants to
    author outside of any pack. The new row lands with ``is_system=False``.

    Pass ``assigned_to_id`` to simultaneously start a live Quest instance
    for a specific child. Omit to just author the definition.
    """
    parent = require_parent()
    required_badge = None
    if params.required_badge_id is not None:
        try:
            required_badge = Badge.objects.get(pk=params.required_badge_id)
        except Badge.DoesNotExist:
            raise MCPValidationError(
                f"required_badge_id {params.required_badge_id} not found.",
            )
    if QuestDefinition.objects.filter(name=params.name).exists():
        raise MCPValidationError(
            f"A quest named {params.name!r} already exists.",
        )

    try:
        validate_trigger_filter(params.trigger_filter)
    except DjangoValidationError as exc:
        raise MCPValidationError("; ".join(exc.messages))

    definition = QuestDefinition.objects.create(
        name=params.name,
        description=params.description,
        icon=params.icon,
        quest_type=params.quest_type,
        target_value=params.target_value,
        duration_days=params.duration_days,
        trigger_filter=params.trigger_filter,
        coin_reward=params.coin_reward,
        xp_reward=params.xp_reward,
        is_repeatable=params.is_repeatable,
        is_system=False,
        required_badge=required_badge,
        created_by=parent,
    )

    result: dict[str, Any] = {
        "definition": _definition_to_dict(definition),
        "quest": None,
    }
    if params.assigned_to_id is not None:
        try:
            child = User.objects.get(pk=params.assigned_to_id, role="child")
        except User.DoesNotExist:
            raise MCPValidationError(
                f"assigned_to_id {params.assigned_to_id} does not match any child.",
            )
        try:
            quest = QuestService.start_quest(child, definition.pk)
        except ValueError as exc:
            raise MCPValidationError(str(exc))
        result["quest"] = _quest_to_dict(quest)

    return result


@tool()
@safe_tool
def assign_quest(params: AssignQuestIn) -> dict[str, Any]:
    """Start a live Quest for a specific child from an existing QuestDefinition.

    Parent-only. Mirrors ``POST /api/quests/{id}/assign/``. Raises if the
    child already has an active quest or doesn't meet the badge gate.
    """
    require_parent()
    try:
        child = User.objects.get(pk=params.user_id, role="child")
    except User.DoesNotExist:
        raise MCPValidationError(
            f"user_id {params.user_id} does not match any child.",
        )
    if not QuestDefinition.objects.filter(pk=params.definition_id).exists():
        raise MCPNotFoundError(
            f"QuestDefinition {params.definition_id} not found.",
        )
    try:
        quest = QuestService.start_quest(child, params.definition_id)
    except ValueError as exc:
        raise MCPValidationError(str(exc))
    return _quest_to_dict(quest)


@tool()
@safe_tool
def assign_co_op_quest(params: AssignCoOpQuestIn) -> dict[str, Any]:
    """Start ONE shared Quest with 2+ children as participants.

    Parent-only. All children contribute to a single shared HP/collection
    pool (``target_value``), and every participant receives the full
    reward bundle on completion. Fails atomically if any participant is
    already on an active quest or lacks the required badge.

    The first UI to wire this up is parent Manage → Quests. Frontend can
    present it as a "Family Co-op" flow; backend enforces no-partial-state.
    """
    require_parent()
    users = list(User.objects.filter(pk__in=params.user_ids, role="child"))
    if len(users) != len(params.user_ids):
        found = {u.pk for u in users}
        missing = [uid for uid in params.user_ids if uid not in found]
        raise MCPValidationError(
            f"user_ids don't match any child: {missing}",
        )
    if not QuestDefinition.objects.filter(pk=params.definition_id).exists():
        raise MCPNotFoundError(
            f"QuestDefinition {params.definition_id} not found.",
        )
    try:
        quest = QuestService.start_co_op_quest(params.definition_id, users)
    except ValueError as exc:
        raise MCPValidationError(str(exc))
    return _quest_to_dict(quest)


@tool()
@safe_tool
def delete_quest_definition(params: DeleteQuestDefinitionIn) -> dict[str, Any]:
    """Permanently remove a QuestDefinition (parent-only).

    Cascades: every live ``Quest`` instance and its participants / progress
    rows go with the definition. Use for cleaning up smoke-test or stale
    parent-authored definitions. For day-to-day cancellation of an active
    run, use ``cancel_quest`` instead (which just flips the Quest status).
    """
    require_parent()
    try:
        definition = QuestDefinition.objects.get(pk=params.quest_definition_id)
    except QuestDefinition.DoesNotExist:
        raise MCPNotFoundError(
            f"QuestDefinition {params.quest_definition_id} not found.",
        )
    definition_id = definition.pk
    name = definition.name
    definition.delete()
    return {"quest_definition_id": definition_id, "name": name, "deleted": True}


@tool()
@safe_tool
def cancel_quest(params: CancelQuestIn) -> dict[str, Any]:
    """Mark an active quest as ``failed`` (parent-only).

    Use this to cancel / abandon a quest mid-run — doesn't refund the
    quest scroll (if one was used to start it).
    """
    require_parent()
    try:
        quest = Quest.objects.get(pk=params.quest_id)
    except Quest.DoesNotExist:
        raise MCPNotFoundError(f"Quest {params.quest_id} not found.")
    if quest.status != Quest.Status.ACTIVE:
        raise MCPValidationError(
            f"Quest is {quest.status!r}, not active; cannot cancel.",
        )
    quest.status = Quest.Status.FAILED
    quest.save(update_fields=["status", "updated_at"])
    return _quest_to_dict(quest)


@tool()
@safe_tool
def set_quest_definition_skill_tags(
    params: SetQuestDefinitionSkillTagsIn,
) -> dict[str, Any]:
    """Replace the skill tags on a QuestDefinition (parent-only).

    On completion, the definition's ``xp_reward`` pool is split across
    these tags by ``xp_weight``. Passing an empty list removes all tags
    and the quest awards coins + items only (no skill-tree credit) —
    matches the pre-2026-04-21 behavior for untagged quests.
    """
    from apps.achievements.models import Skill
    from apps.quests.serializers import QuestDefinitionSerializer

    require_parent()
    try:
        definition = QuestDefinition.objects.get(pk=params.quest_definition_id)
    except QuestDefinition.DoesNotExist:
        raise MCPNotFoundError(
            f"QuestDefinition {params.quest_definition_id} not found.",
        )

    skill_ids = [t.skill_id for t in params.skill_tags]
    known = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [s for s in skill_ids if s not in known]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs: {missing}")

    with transaction.atomic():
        QuestSkillTag.objects.filter(quest_definition=definition).delete()
        QuestSkillTag.objects.bulk_create([
            QuestSkillTag(
                quest_definition=definition,
                skill_id=t.skill_id,
                xp_weight=t.xp_weight,
            )
            for t in params.skill_tags
        ])
    definition.refresh_from_db()
    return to_plain(QuestDefinitionSerializer(definition).data)
