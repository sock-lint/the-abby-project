"""Helpers for creating notifications.

Previously lived at ``apps/projects/notifications.py``. Imports now point
here: ``from apps.notifications.services import notify, notify_parents``.
"""
from .models import Notification


def get_display_name(user):
    """Return a human-readable name for the user."""
    return getattr(user, "display_name", None) or user.username


def notify(user, title, message="", notification_type="timecard_ready", link=""):
    """Create an in-app notification."""
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )


def notify_parents(
    title,
    message,
    notification_type,
    link="",
    *,
    family=None,
    about_user=None,
):
    """Send a notification to every active parent in a family.

    Either ``family`` or ``about_user`` must be passed; ``about_user`` is the
    common case (an event happened to a child) — we derive their family.
    Without one of these we refuse to fan out, otherwise a missed-update
    would silently blast every parent in every family.
    """
    if family is None and about_user is not None:
        family = getattr(about_user, "family", None)
    if family is None:
        raise ValueError(
            "notify_parents requires family= or about_user= so notifications "
            "stay scoped to a single household."
        )
    # Imported lazily to avoid a module-load dep from notifications → projects.
    from apps.accounts.models import User

    parents = User.objects.filter(
        role="parent", is_active=True, family=family,
    )
    for parent in parents:
        notify(parent, title, message, notification_type, link=link)
