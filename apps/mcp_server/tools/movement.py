"""Movement-session MCP tools.

Mirrors the REST surface at ``/api/movement-types/`` + ``/api/movement-sessions/``
plus a staff-parent-only ``set_movement_type_skill_tags`` shortcut so an LLM can wire
a freshly-authored MovementType to skills in one call.

The first ``MovementSessionService.DAILY_REWARD_LIMIT`` sessions per local day
fire XP + drops + game loop; subsequent logs write the row but skip rewards.
The counter survives delete (anti-farm), so log → delete → log on the same day
won't re-arm rewards. See the "Movement sessions" gotcha in CLAUDE.md.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.movement.models import (
    MovementSession,
    MovementType,
    MovementTypeSkillTag,
)
from apps.movement.services import MovementSessionError, MovementSessionService

from ..context import get_current_user, get_in_family, resolve_target_user, require_staff_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..schemas import (
    DeleteMovementSessionIn,
    GetMovementSessionIn,
    ListMovementSessionsIn,
    ListMovementTypesIn,
    LogMovementSessionIn,
    SetMovementTypeSkillTagsIn,
)
from ..server import tool
from ..retries import mutation_once
from ..shapes import many, movement_session_to_dict, movement_type_to_dict


@tool()
@safe_tool
def list_movement_types(params: ListMovementTypesIn) -> dict[str, Any]:
    """Read-only catalog of MovementType rows."""
    get_current_user()
    qs = MovementType.objects.all()
    if params.active_only:
        qs = qs.filter(is_active=True)
    return {"movement_types": many(qs.order_by("order", "name"), movement_type_to_dict)}


@tool()
@safe_tool
def list_movement_sessions(params: ListMovementSessionsIn) -> dict[str, Any]:
    """List logged sessions. Children see their own; parents see any child."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = MovementSession.objects.select_related("movement_type", "user").filter(user=target)
    if params.since:
        qs = qs.filter(occurred_on__gte=params.since)
    qs = qs.order_by("-occurred_on", "-created_at")[: params.limit]
    return {"sessions": many(qs, movement_session_to_dict)}


@tool()
@safe_tool
def get_movement_session(params: GetMovementSessionIn) -> dict[str, Any]:
    """Fetch a single session. Children may only read their own."""
    user = get_current_user()
    session = get_in_family(MovementSession, params.session_id, actor=user)
    if user.role != "parent" and session.user_id != user.id:
        raise MCPPermissionDenied("Children can only read their own sessions.")
    return movement_session_to_dict(session)


@tool()
@safe_tool
def log_movement_session(params: LogMovementSessionIn) -> dict[str, Any]:
    """Log a self-reported physical-activity session.

    Children log for themselves; parents can pass ``user_id`` to log on a
    child's behalf. Supply a stable client_request_id UUID, optionally with
    measured distance and mi/km units. Identical retries return the original
    session and reward/challenge receipts without advancing counters again.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    try:
        movement_type = MovementType.objects.get(pk=params.movement_type_id)
    except MovementType.DoesNotExist:
        raise MCPNotFoundError(f"MovementType {params.movement_type_id} not found.")

    def create(actor, fresh_target):
        try:
            return MovementSessionService.log_session(
                fresh_target, movement_type=movement_type,
                duration_minutes=params.duration_minutes, intensity=params.intensity,
                notes=params.notes, distance=params.distance, distance_unit=params.distance_unit,
                client_request_id=params.client_request_id,
            )
        except MovementSessionError as exc:
            raise MCPValidationError(str(exc)) from exc

    return mutation_once(
        actor=user, target=target, operation="log_movement_session", request_id=params.client_request_id,
        payload=params.model_dump(exclude={"client_request_id", "user_id"}), result_model=MovementSession,
        shared_target_request=True, create=create, serialize=movement_session_to_dict,
    )


@tool()
@safe_tool
def delete_movement_session(params: DeleteMovementSessionIn) -> dict[str, Any]:
    """Remove a session row. Owner or parent only. Counter is NOT decremented."""
    user = get_current_user()
    session = get_in_family(MovementSession, params.session_id, actor=user)
    if user.role != "parent" and session.user_id != user.id:
        raise MCPPermissionDenied("You can only delete your own sessions.")
    session.delete()
    return {"deleted": True, "session_id": params.session_id}


@tool()
@safe_tool
def set_movement_type_skill_tags(params: SetMovementTypeSkillTagsIn) -> dict[str, Any]:
    """Replace the skill-tag fan-out on a MovementType (staff-parent-only).

    Distribution mirrors ChoreSkillTag — the per-session XP pool is split
    across these tags by ``xp_weight``. Empty list strips tags.
    """
    from apps.achievements.models import Skill

    require_staff_parent()
    try:
        mt = MovementType.objects.get(pk=params.movement_type_id)
    except MovementType.DoesNotExist:
        raise MCPNotFoundError(f"MovementType {params.movement_type_id} not found.")

    skill_ids = [t.skill_id for t in params.skill_tags]
    known = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [s for s in skill_ids if s not in known]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs: {missing}")

    with transaction.atomic():
        MovementTypeSkillTag.objects.filter(movement_type=mt).delete()
        MovementTypeSkillTag.objects.bulk_create([
            MovementTypeSkillTag(movement_type=mt, skill_id=t.skill_id, xp_weight=t.xp_weight)
            for t in params.skill_tags
        ])
    mt.refresh_from_db()
    return movement_type_to_dict(mt)
