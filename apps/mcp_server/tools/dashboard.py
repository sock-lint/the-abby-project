"""Aggregated dashboard MCP tool."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.achievements.models import UserBadge
from apps.payments.services import PaymentService
from apps.notifications.models import Notification
from apps.accounts.models import User
from apps.projects.models import Project
from apps.rewards.models import RewardRedemption
from apps.rewards.services import CoinService
from apps.timecards.models import TimeEntry
from apps.timecards.services import ClockService, TimeEntryService

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import GetDashboardIn
from ..server import tool
from ..shapes import (
    project_list_to_dict,
    time_entry_to_dict,
    user_badge_to_dict,
    user_to_dict,
)


def _build_user_dashboard(target: User) -> dict[str, Any]:
    active = ClockService.get_active_entry(target)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_minutes = TimeEntry.objects.filter(
        user=target, status="completed", clock_in__date__gte=week_start,
    ).aggregate(total=Sum("duration_minutes"))["total"] or 0

    active_projects = list(
        Project.objects.filter(
            assigned_to=target, status__in=["active", "in_progress"],
        ).order_by("-created_at")[:5]
    )
    recent_badges = list(
        UserBadge.objects.select_related("badge")
        .filter(user=target).order_by("-earned_at")[:5]
    )
    pending_redemptions = RewardRedemption.objects.filter(
        user=target, status=RewardRedemption.Status.PENDING,
    ).count()
    unread_notifications = Notification.objects.filter(
        user=target, is_read=False,
    ).count()

    return {
        "user": user_to_dict(target),
        "coin_balance": int(CoinService.get_balance(target)),
        "payment_balance": str(PaymentService.get_balance(target)),
        "active_entry": time_entry_to_dict(active) if active else None,
        "current_streak": TimeEntryService.current_streak(target),
        "hours_this_week": round(week_minutes / 60, 1),
        "pending_redemptions": pending_redemptions,
        "unread_notifications": unread_notifications,
        "active_projects": [project_list_to_dict(p) for p in active_projects],
        "recent_badges": [user_badge_to_dict(ub) for ub in recent_badges],
    }


@tool()
@safe_tool
def get_dashboard(params: GetDashboardIn) -> dict[str, Any]:
    """Return an aggregated dashboard view.

    Parents without a ``user_id`` see their own dashboard plus a per-child
    rollup under ``children``. Children are always scoped to themselves.
    """
    user = get_current_user()
    target_id = params.user_id if params.user_id is not None else user.id
    if target_id != user.id and user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own dashboard.")

    try:
        target = User.objects.get(pk=target_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {target_id} not found.")

    result = _build_user_dashboard(target)

    if user.role == "parent" and params.user_id is None:
        children = User.objects.filter(role="child").order_by("display_name", "username")
        result["children"] = [_build_user_dashboard(c) for c in children]

    return result
