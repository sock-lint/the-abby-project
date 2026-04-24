"""Notification MCP tools."""
from __future__ import annotations

from typing import Any

from apps.notifications.models import Notification

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    GetUnreadNotificationCountIn,
    ListNotificationsIn,
    MarkAllNotificationsReadIn,
    MarkNotificationReadIn,
)
from ..server import tool
from ..shapes import notification_to_dict


@tool()
@safe_tool
def list_notifications(params: ListNotificationsIn) -> dict[str, Any]:
    """List notifications for the current user."""
    user = get_current_user()
    qs = Notification.objects.filter(user=user)
    unread_count = qs.filter(is_read=False).count()
    if params.unread_only:
        qs = qs.filter(is_read=False)
    qs = qs.order_by("-created_at")[: params.limit]
    return {
        "notifications": [notification_to_dict(n) for n in qs],
        "unread_count": unread_count,
    }


@tool()
@safe_tool
def mark_notification_read(params: MarkNotificationReadIn) -> dict[str, Any]:
    """Mark a single notification as read."""
    user = get_current_user()
    try:
        notification = Notification.objects.get(pk=params.notification_id)
    except Notification.DoesNotExist:
        raise MCPNotFoundError(f"Notification {params.notification_id} not found.")

    if notification.user_id != user.id:
        raise MCPPermissionDenied("Cannot modify another user's notifications.")

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return notification_to_dict(notification)


@tool()
@safe_tool
def mark_all_notifications_read(params: MarkAllNotificationsReadIn) -> dict[str, Any]:
    """Bulk mark every unread notification for the caller as read."""
    user = get_current_user()
    updated = user.notifications.filter(is_read=False).update(is_read=True)
    return {"marked_read": updated}


@tool()
@safe_tool
def get_unread_notification_count(params: GetUnreadNotificationCountIn) -> dict[str, Any]:
    """Return the count of unread notifications for the caller."""
    user = get_current_user()
    return {"count": user.notifications.filter(is_read=False).count()}
