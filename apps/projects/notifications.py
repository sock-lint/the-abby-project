from .models import Notification


def notify(user, title, message="", notification_type="timecard_ready"):
    """Create an in-app notification."""
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
    )
