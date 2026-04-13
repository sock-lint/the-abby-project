from .models import Notification, User


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


def notify_parents(title, message, notification_type, link=""):
    """Send a notification to every parent user."""
    for parent in User.objects.filter(role="parent"):
        notify(parent, title, message, notification_type, link=link)
