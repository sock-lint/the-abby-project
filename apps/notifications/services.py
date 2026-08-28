"""Helpers for creating notifications.

Previously lived at ``apps/projects/notifications.py``. Imports now point
here: ``from apps.notifications.services import notify, notify_parents``.
"""
import logging

from .models import Notification

logger = logging.getLogger(__name__)


def get_display_name(user):
    """Return a human-readable name for the user."""
    return getattr(user, "display_name", None) or user.username


def notify(user, title, message="", notification_type="timecard_ready", link=""):
    """Create an in-app notification and push it to the user's devices.

    This is the single chokepoint every notification in the app flows
    through, so hooking push here reaches all 40+ NotificationTypes without
    touching a single call site.

    The in-app row is created FIRST and is what callers get back; push is a
    best-effort side channel layered on top. If the broker is unreachable or
    push isn't configured, the bell still works exactly as before.
    """
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )
    _push(notification)
    return notification


def _push(notification):
    """Hand the notification to the push task. Never raises."""
    from .push import push_enabled

    # Cheap local check first so an unconfigured deployment doesn't queue a
    # task per notification just to have it no-op on the worker.
    if not push_enabled():
        return
    try:
        from .tasks import send_push_notification

        send_push_notification.delay(
            notification.user_id,
            notification.title,
            notification.message,
            notification.link,
            notification.notification_type,
        )
    except Exception:  # noqa: BLE001 — a dead broker must not break notify()
        logger.exception("Could not queue push for notification %s", notification.pk)


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
