"""Timecard-related MCP tools.

Clock-in / clock-out are intentionally NOT exposed here — timers stay a
direct-app action per the MCP plan so an LLM can't accidentally accrue
paid hours. Clock state is only *read* via ``get_active_entry`` and
``list_time_entries``. Approvals run through the existing
``TimecardService.approve_timecard`` flow.
"""
from __future__ import annotations

from typing import Any

from apps.projects.models import User
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import ClockService, TimecardService

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    ApproveTimecardIn,
    GetActiveEntryIn,
    ListTimeEntriesIn,
    ListTimecardsIn,
)
from ..server import mcp
from ..shapes import time_entry_to_dict, timecard_to_dict


def _resolve_target(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own time data.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@mcp.tool()
@safe_tool
def list_time_entries(params: ListTimeEntriesIn) -> dict[str, Any]:
    """List TimeEntry rows for a user (children forced to self)."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    qs = TimeEntry.objects.select_related("project").filter(user=target)
    if params.status:
        qs = qs.filter(status=params.status)
    if params.since:
        qs = qs.filter(clock_in__date__gte=params.since)
    qs = qs.order_by("-clock_in")[: params.limit]

    return {"entries": [time_entry_to_dict(e) for e in qs]}


@mcp.tool()
@safe_tool
def get_active_entry(params: GetActiveEntryIn) -> dict[str, Any]:
    """Return the user's current active TimeEntry, or null if not clocked in."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)
    entry = ClockService.get_active_entry(target)
    return {"entry": time_entry_to_dict(entry) if entry else None}


@mcp.tool()
@safe_tool
def list_timecards(params: ListTimecardsIn) -> dict[str, Any]:
    """List weekly timecards for a user (children forced to self)."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    qs = Timecard.objects.filter(user=target)
    if params.status:
        qs = qs.filter(status=params.status)
    qs = qs.order_by("-week_start")[: params.limit]

    return {"timecards": [timecard_to_dict(tc) for tc in qs]}


@mcp.tool()
@safe_tool
def approve_timecard(params: ApproveTimecardIn) -> dict[str, Any]:
    """Approve a weekly timecard (parent-only).

    Delegates to :meth:`TimecardService.approve_timecard`, which stamps
    audit fields and re-evaluates badges for the timecard owner.
    """
    parent = require_parent()
    try:
        timecard = Timecard.objects.select_related("user").get(pk=params.timecard_id)
    except Timecard.DoesNotExist:
        raise MCPNotFoundError(f"Timecard {params.timecard_id} not found.")

    updated = TimecardService.approve_timecard(timecard, parent, notes=params.notes)
    return timecard_to_dict(updated)
