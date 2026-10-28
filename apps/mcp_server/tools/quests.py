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


from django.core.exceptions import ValidationError as DjangoValidationError

from django.db import transaction
from django.db.models import Q

from apps.achievements.models import Badge
from apps.accounts.models import User
from apps.quests.models import Quest, QuestDefinition, QuestSkillTag
from apps.quests.queries import definitions_visible_to
from apps.quests.services import QuestService
from apps.quests.validators import validate_trigger_filter

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import (
    MCPNotFoundError,
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
from ..legacy_household import household_context, household_operation, locked_member_ids
from ..server import tool
from ..retries import mutation_once
from ..shapes import to_plain


# ---------------------------------------------------------------------------
# Serializer helpers
# ---------------------------------------------------------------------------


def _quest_to_dict(quest: Quest) -> dict[str, Any]:
    from apps.quests.serializers import QuestSerializer

    payload = to_plain(QuestSerializer(quest, context={"observer_family_id": get_current_user().family_id}).data)
    selected = locked_member_ids(required=False)
    if selected is not None:
        from apps.quests.participants import FORMER_PARTICIPANT
        for participant in payload["participants"]:
            if participant["user"] not in selected:
                participant["user_name"] = FORMER_PARTICIPANT
    return payload


def _definition_to_dict(d: QuestDefinition) -> dict[str, Any]:
    from apps.quests.serializers import QuestDefinitionSerializer

    return to_plain(QuestDefinitionSerializer(d).data)


def _visible_definitions(actor):
    return definitions_visible_to(actor).filter(Q(is_system=True) | Q(created_by_id__in=locked_member_ids()))


def _visible_instances(actor):
    """Read personal instances for self and household child supervision."""
    queryset = Quest.objects.select_related("definition").prefetch_related("participants")
    if actor.role == "parent":
        return queryset.filter(
            Q(participants__user=actor)
            | Q(participants__user__family_id=actor.family_id,
                participants__user__role="child", participants__user_id__in=locked_member_ids()),
        ).distinct()
    return queryset.filter(participants__user=actor).distinct()


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_quests(params: ListQuestsIn) -> dict[str, Any]:
    """List quests visible to the current user.

    Children see their own participations; parents see their own and their
    family's children, or filter to self/a child with ``user_id``.

    Audit C8: parent path was previously unscoped — returned every
    family's quests to every parent in the deployment.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    with household_context(
        user, target, allow_inactive_target=True,
        family_members=True,
    ) as (user, target):
        if target.pk != user.pk and target.role != "child":
            raise MCPNotFoundError(f"User {params.user_id} not found.")
        qs = _visible_instances(user)
        if params.user_id is not None:
            qs = qs.filter(participants__user=target)
        if not params.include_completed:
            qs = qs.filter(status=Quest.Status.ACTIVE)
        qs = qs.distinct().order_by("-start_date")[: params.limit]
        return {"quests": [_quest_to_dict(q) for q in qs]}


@tool()
@safe_tool
@household_operation(family_members=True)
def get_quest(params: GetQuestIn) -> dict[str, Any]:
    """Get a quest instance with its progress + participants.

    Parents read self or current household children; children read themselves.
    Shared definition authoring remains separate from accepted instances.
    """
    user = get_current_user()
    qs = _visible_instances(user)
    try:
        quest = qs.get(pk=params.quest_id)
    except Quest.DoesNotExist:
        raise MCPNotFoundError(f"Quest {params.quest_id} not found.")
    return _quest_to_dict(quest)


@tool()
@safe_tool
@household_operation(family_members=True)
def list_quest_catalog(params: ListQuestCatalogIn) -> dict[str, Any]:
    """Browse available authored QuestDefinition choices. Parent-only.

    This is the "catalog" the LLM inspects to pick a definition id for
    ``assign_quest``. Filter with ``quest_type`` to narrow to boss or
    collection quests. Retired taxonomy is hidden from new choices; saved
    quests and the global management catalog retain their original identities.
    """
    actor = require_parent()
    from apps.quests.reference_locks import definitions_with_available_taxonomy
    visible = _visible_definitions(actor)
    qs = definitions_with_available_taxonomy(visible).prefetch_related(
        "reward_items__item__pet_species__available_potions", "reward_items__item__potion_type",
    )
    if params.quest_type:
        qs = qs.filter(quest_type=params.quest_type)
    qs = qs.order_by("quest_type", "name")
    from apps.quests.availability import definition_is_available
    from apps.quests.progress_sources import has_progress_source
    return {"quest_definitions": [_definition_to_dict(d) for d in qs
                                  if definition_is_available(d)
                                  and has_progress_source(d.quest_type, d.trigger_filter)]}


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@tool()
@safe_tool
@transaction.atomic
def create_quest_definition(
    params: CreateQuestDefinitionIn,
) -> dict[str, Any]:
    """Create a custom QuestDefinition (parent-only).

    For system / bundled quests, prefer shipping them in a content pack's
    ``quests.yaml`` — this tool is for one-off quests a parent wants to
    author outside of any pack. The new row lands with ``is_system=False``.

    Pass ``assigned_to_id`` to simultaneously start a live Quest instance
    for a specific child. Omit to just author the definition. Creation and
    assignment commit together. Supply request_id for duplicate-safe retries;
    reuse that UUID only with identical details.
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
    child = None
    if params.assigned_to_id is not None:
        child = resolve_target_user(parent, params.assigned_to_id)
        if getattr(child, "role", None) != "child":
            raise MCPValidationError(f"assigned_to_id {params.assigned_to_id} does not match any child.")

    def create(actor, target):
        # New rules must match typed source evidence. Exact saved UUID replay
        # precedes this guard, preserving previously accepted definitions.
        try:
            validate_trigger_filter(params.trigger_filter)
        except DjangoValidationError as exc:
            raise MCPValidationError("; ".join(exc.messages)) from exc
        # Only new authoring needs a reachable activity. A saved UUID replay
        # returns its original promise before entering this callback.
        from apps.quests.progress_sources import require_progress_source
        require_progress_source(params.quest_type, params.trigger_filter)
        if definitions_visible_to(actor).filter(name=params.name).exists():
            raise MCPValidationError(f"A quest named {params.name!r} already exists.")
        definition = QuestDefinition.objects.create(
            name=params.name, description=params.description, icon=params.icon,
            quest_type=params.quest_type, target_value=params.target_value,
            duration_days=params.duration_days, trigger_filter=params.trigger_filter,
            coin_reward=params.coin_reward, xp_reward=params.xp_reward,
            is_repeatable=params.is_repeatable, is_system=False,
            required_badge=required_badge, created_by=actor,
        )
        from apps.quests.reference_locks import lock_filter_category
        lock_filter_category(definition.trigger_filter)
        return QuestService.start_quest(target, definition.pk) if child is not None else definition

    def serialize(result):
        assigned = result if child is not None else None
        definition = assigned.definition if assigned else result
        return {"definition": _definition_to_dict(definition), "quest": _quest_to_dict(assigned) if assigned else None}

    if params.request_id is not None:
        return mutation_once(
            actor=parent, target=child or parent, operation="create_quest_definition", request_id=params.request_id,
            payload=params.model_dump(exclude={"request_id"}), result_model=Quest if child is not None else QuestDefinition,
            target_field="participants__user_id" if child is not None else "created_by_id", create=create, serialize=serialize,
        )
    with household_context(parent, child or parent) as (fresh_parent, fresh_target):
        return serialize(create(fresh_parent, fresh_target))


@tool()
@safe_tool
def assign_quest(params: AssignQuestIn) -> dict[str, Any]:
    """Start a live Quest for a specific child from an existing QuestDefinition.

    Parent-only. Mirrors ``POST /api/quests/{id}/assign/``. Raises if the
    child already has an active quest or doesn't meet the badge gate.
    """
    parent = require_parent()
    child = resolve_target_user(parent, params.user_id)
    with household_context(parent, child, family_members=True) as (parent, child):
        if getattr(child, "role", None) != "child":
            raise MCPValidationError(
                f"user_id {params.user_id} does not match any child.",
            )
        if not _visible_definitions(parent).filter(pk=params.definition_id).exists():
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
@household_operation(family_members=True)
def assign_co_op_quest(params: AssignCoOpQuestIn) -> dict[str, Any]:
    """Start ONE shared Quest with 2+ children as participants.

    Parent-only. All children contribute to a single shared HP/collection
    pool (``target_value``), and every participant receives the full
    reward bundle on completion. Fails atomically if any participant is
    already on an active quest or lacks the required badge.

    The first UI to wire this up is parent Manage → Quests. Frontend can
    present it as a "Family Co-op" flow; backend enforces no-partial-state.
    """
    parent = require_parent()
    users = list(
        User.objects.filter(
            pk__in=set(params.user_ids) & locked_member_ids(),
            role="child",
            family=parent.family,
        )
    )
    if len(users) != len(params.user_ids):
        found = {u.pk for u in users}
        missing = [uid for uid in params.user_ids if uid not in found]
        raise MCPValidationError(
            f"user_ids don't match any child: {missing}",
        )
    if not _visible_definitions(parent).filter(pk=params.definition_id).exists():
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
@household_operation(family_members=True)
def delete_quest_definition(params: DeleteQuestDefinitionIn) -> dict[str, Any]:
    """Permanently remove a parent-authored QuestDefinition (parent-only).

    Cascades: every live ``Quest`` instance and its participants / progress
    rows go with the definition. Use for cleaning up smoke-test or stale
    parent-authored definitions. For day-to-day cancellation of an active
    run, use ``cancel_quest`` instead (which just flips the Quest status).

    Audit C8: scope to parent-authored definitions in the caller's family.
    System quests (``is_system=True``) come from content packs — they are
    global content and can't be deleted via MCP. Parent-authored quests
    can only be deleted by a parent in the creating parent's family.
    """
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(
            f"QuestDefinition {params.quest_definition_id} not found.",
        )
    try:
        definition = QuestDefinition.objects.get(
            pk=params.quest_definition_id,
            is_system=False,
            created_by__family_id=family_id,
            created_by_id__in=locked_member_ids(),
        )
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
@household_operation(family_members=True)
def cancel_quest(params: CancelQuestIn) -> dict[str, Any]:
    """Mark an active quest as ``failed`` (parent-only).

    Use this to cancel / abandon a quest mid-run — doesn't refund the
    quest scroll (if one was used to start it).

    Audit C8: family-scope so a parent can't cancel another family's
    active quest.
    """
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Quest {params.quest_id} not found.")
    try:
        quest = Quest.objects.filter(
            participants__user__family_id=family_id, participants__user_id__in=locked_member_ids(),
        ).distinct().get(pk=params.quest_id)
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
@household_operation(family_members=True)
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

    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(
            f"QuestDefinition {params.quest_definition_id} not found.",
        )
    # Audit C8: scope to parent-authored definitions in the caller's
    # family. System quests are global content and shouldn't be retagged
    # via MCP — same gate as ``delete_quest_definition``.
    try:
        definition = QuestDefinition.objects.get(
            pk=params.quest_definition_id,
            is_system=False,
            created_by__family_id=family_id,
            created_by_id__in=locked_member_ids(),
        )
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
        from apps.quests.reference_locks import lock_definition_write
        lock_definition_write()
        from apps.rpg.taxonomy_references import admit_references
        admit_references(Skill, skill_ids,
                         retained_ids=definition.skill_tags.values_list("skill_id", flat=True))
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
