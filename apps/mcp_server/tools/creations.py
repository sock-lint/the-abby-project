"""Creations MCP tools — child-authored "I made a thing" entries.

Mirrors the REST surface at ``/api/creations/`` including the bonus
approval flow. Image + audio bytes are passed as base64 (no multipart
upload over MCP). The first 2 logs per local day fire baseline XP +
drop + game loop; subsequent logs land silently in Sketchbook/Yearbook
without rewards. Counter survives delete (anti-farm). See the
"Creations" gotcha in CLAUDE.md.
"""
from __future__ import annotations

import base64
from typing import Any

from django.core.files.base import ContentFile

from apps.creations.models import Creation
from apps.creations.services import CreationService

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..schemas import (
    ApproveCreationIn,
    DeleteCreationIn,
    GetCreationIn,
    ListCreationsIn,
    ListPendingCreationsIn,
    LogCreationIn,
    RejectCreationIn,
    SubmitCreationIn,
)
from ..server import tool
from ..shapes import creation_to_dict, many


def _decode_b64(label: str, value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise MCPValidationError(f"{label} is not valid base64: {exc}")


@tool()
@safe_tool
def list_creations(params: ListCreationsIn) -> dict[str, Any]:
    """List creations. Children see their own; parents see any child."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    qs = Creation.objects.select_related(
        "primary_skill", "primary_skill__category", "secondary_skill", "user",
    ).filter(user=target)
    if params.status:
        qs = qs.filter(status=params.status)
    qs = qs.order_by("-created_at")[: params.limit]
    return {"creations": many(qs, creation_to_dict)}


@tool()
@safe_tool
def get_creation(params: GetCreationIn) -> dict[str, Any]:
    """Fetch a single creation. Children may only read their own."""
    user = get_current_user()
    try:
        creation = Creation.objects.select_related(
            "primary_skill", "secondary_skill", "user",
        ).get(pk=params.creation_id)
    except Creation.DoesNotExist:
        raise MCPNotFoundError(f"Creation {params.creation_id} not found.")
    if user.role != "parent" and creation.user_id != user.id:
        raise MCPPermissionDenied("Children can only read their own creations.")
    return creation_to_dict(creation)


@tool()
@safe_tool
def log_creation(params: LogCreationIn) -> dict[str, Any]:
    """Log a child-authored Creation row.

    The first 2 per local day award XP + drop + game loop; subsequent
    logs write silently. Always emits a Chronicle CREATION entry.
    Children log for themselves; parents may pass ``user_id`` to log
    on behalf.
    """
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

    image_bytes = _decode_b64("image_b64", params.image_b64)
    image_file = ContentFile(image_bytes, name=f"creation-{target.id}.jpg")

    audio_file = None
    if params.audio_b64:
        audio_bytes = _decode_b64("audio_b64", params.audio_b64)
        audio_file = ContentFile(audio_bytes, name=f"creation-{target.id}.m4a")

    creation = CreationService.log_creation(
        target,
        image=image_file,
        audio=audio_file,
        caption=params.caption,
        primary_skill_id=params.primary_skill_id,
        secondary_skill_id=params.secondary_skill_id,
    )
    return creation_to_dict(creation)


@tool()
@safe_tool
def delete_creation(params: DeleteCreationIn) -> dict[str, Any]:
    """Delete a creation (owner or parent). Blob-first; counter NOT decremented."""
    user = get_current_user()
    try:
        creation = Creation.objects.get(pk=params.creation_id)
    except Creation.DoesNotExist:
        raise MCPNotFoundError(f"Creation {params.creation_id} not found.")
    if user.role != "parent" and creation.user_id != user.id:
        raise MCPPermissionDenied("You can only delete your own creations.")
    if creation.image:
        creation.image.delete(save=False)
    if creation.audio:
        creation.audio.delete(save=False)
    creation.delete()
    return {"deleted": True, "creation_id": params.creation_id}


@tool()
@safe_tool
def submit_creation(params: SubmitCreationIn) -> dict[str, Any]:
    """Submit a Creation for parent bonus approval (owner or parent)."""
    user = get_current_user()
    try:
        creation = Creation.objects.select_related("primary_skill", "user").get(
            pk=params.creation_id,
        )
    except Creation.DoesNotExist:
        raise MCPNotFoundError(f"Creation {params.creation_id} not found.")
    if user.role != "parent" and creation.user_id != user.id:
        raise MCPPermissionDenied("Only the owner or a parent can submit.")
    updated = CreationService.submit_for_bonus(creation)
    return creation_to_dict(updated)


@tool()
@safe_tool
def approve_creation(params: ApproveCreationIn) -> dict[str, Any]:
    """Approve a Creation's bonus pool (parent-only).

    ``bonus_xp`` defaults to 15. ``skill_tags`` is a parent-authored
    distribution; empty falls back to the child's primary skill at
    weight 1. Baseline XP from the original log is NOT re-awarded.
    """
    parent = require_parent()
    try:
        creation = Creation.objects.select_related("primary_skill", "user").get(
            pk=params.creation_id,
        )
    except Creation.DoesNotExist:
        raise MCPNotFoundError(f"Creation {params.creation_id} not found.")
    extra = [
        {"skill_id": t.skill_id, "xp_weight": t.xp_weight}
        for t in params.skill_tags
    ]
    updated = CreationService.approve_bonus(
        creation,
        parent,
        bonus_xp=params.bonus_xp,
        extra_skill_tags=extra or None,
        notes=params.notes,
    )
    return creation_to_dict(updated)


@tool()
@safe_tool
def reject_creation(params: RejectCreationIn) -> dict[str, Any]:
    """Reject a Creation's bonus (parent-only). Baseline XP stays intact."""
    parent = require_parent()
    try:
        creation = Creation.objects.select_related("primary_skill", "user").get(
            pk=params.creation_id,
        )
    except Creation.DoesNotExist:
        raise MCPNotFoundError(f"Creation {params.creation_id} not found.")
    updated = CreationService.reject_bonus(creation, parent, notes=params.notes)
    return creation_to_dict(updated)


@tool()
@safe_tool
def list_pending_creations(params: ListPendingCreationsIn) -> dict[str, Any]:
    """Parent-only queue of submitted-pending Creations awaiting bonus review."""
    require_parent()
    qs = Creation.objects.select_related(
        "primary_skill", "primary_skill__category", "user",
    ).filter(status=Creation.Status.PENDING).order_by("-updated_at")[: params.limit]
    return {"creations": many(qs, creation_to_dict)}
