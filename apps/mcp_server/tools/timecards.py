"""Timecard-related MCP tools.

Read-side: ``list_time_entries`` / ``get_active_entry`` / ``list_timecards``.

Write-side (added later): ``clock_in`` / ``clock_out`` / ``void_time_entry``
plus ``generate_timecard`` and ``mark_timecard_paid``. The original
"timers stay a direct-app action" rule has been lifted — the MCP write
surface is now strictly opt-in by an authenticated caller, and the
domain service still enforces quiet hours, project ownership, and the
one-active-entry-per-user invariant. ``approve_timecard`` continues to
delegate to ``TimecardService.approve_timecard``.
"""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.projects.models import Project
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import ClockService, TimecardService

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    ApproveTimecardIn,
    ClockInIn,
    ClockOutIn,
    GenerateTimecardIn,
    GetActiveEntryIn,
    ListTimeEntriesIn,
    ListTimecardsIn,
    MarkTimecardPaidIn,
    VoidTimeEntryIn,
)
from ..server import tool
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


@tool()
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


@tool()
@safe_tool
def get_active_entry(params: GetActiveEntryIn) -> dict[str, Any]:
    """Return the user's current active TimeEntry, or null if not clocked in."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)
    entry = ClockService.get_active_entry(target)
    return {"entry": time_entry_to_dict(entry) if entry else None}


@tool()
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


@tool()
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


@tool()
@safe_tool
def clock_in(params: ClockInIn) -> dict[str, Any]:
    """Start a TimeEntry on a project (child self-scoped, parent on-behalf).

    Enforces ClockService rules: no existing active entry, project assigned
    to the target, project status in (active|in_progress), NOT during
    quiet hours (10pm–7am local). Sets project status to ``in_progress``
    if it was ``active``.
    """
    user = get_current_user()
    target = _resolve_target(user, params.user_id)
    try:
        project = Project.objects.get(pk=params.project_id)
    except Project.DoesNotExist:
        raise MCPNotFoundError(f"Project {params.project_id} not found.")
    entry = ClockService.clock_in(target, project)
    return time_entry_to_dict(entry)


@tool()
@safe_tool
def clock_out(params: ClockOutIn) -> dict[str, Any]:
    """End the active TimeEntry. Awards XP + coins via AwardService and
    fires the RPG game loop (streak, drops, quest progress).
    """
    user = get_current_user()
    target = _resolve_target(user, params.user_id)
    entry = ClockService.clock_out(target, notes=params.notes)
    return time_entry_to_dict(entry)


@tool()
@safe_tool
def void_time_entry(params: VoidTimeEntryIn) -> dict[str, Any]:
    """Void a completed TimeEntry (parent-only). Status flips to ``voided``."""
    require_parent()
    try:
        entry = TimeEntry.objects.select_related("project", "user").get(pk=params.entry_id)
    except TimeEntry.DoesNotExist:
        raise MCPNotFoundError(f"TimeEntry {params.entry_id} not found.")
    entry.status = "voided"
    entry.save(update_fields=["status", "updated_at"] if hasattr(entry, "updated_at") else ["status"])
    return time_entry_to_dict(entry)


@tool()
@safe_tool
def generate_timecard(params: GenerateTimecardIn) -> dict[str, Any]:
    """Generate (or refresh) the weekly timecard for a child (parent-only).

    Returns ``null`` when the child has no completed entries in that week.
    Posts hourly PaymentLedger entries on first creation only.
    """
    parent = require_parent()
    child = resolve_target_user(parent, params.user_id)
    if getattr(child, "role", None) != "child":
        raise MCPNotFoundError(f"Child {params.user_id} not found.")
    timecard = TimecardService.generate_weekly_timecard(child, params.week_start)
    if timecard is None:
        return {"timecard": None}
    return {"timecard": timecard_to_dict(timecard)}


@tool()
@safe_tool
def mark_timecard_paid(params: MarkTimecardPaidIn) -> dict[str, Any]:
    """Mark a timecard PAID and post a negative PaymentLedger payout (parent-only)."""
    parent = require_parent()
    try:
        timecard = Timecard.objects.select_related("user").get(pk=params.timecard_id)
    except Timecard.DoesNotExist:
        raise MCPNotFoundError(f"Timecard {params.timecard_id} not found.")
    amount = params.amount if params.amount is not None else timecard.total_earnings
    updated = TimecardService.mark_paid(timecard, parent, amount)
    return timecard_to_dict(updated)
