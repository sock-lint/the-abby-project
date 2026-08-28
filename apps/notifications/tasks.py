"""Background delivery for out-of-app notifications."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.notifications.tasks.send_push_notification")
def send_push_notification(user_id, title, body="", url="", notification_type=""):
    """Fan one notification out to a user's registered devices.

    Runs off-request because a push round-trip per device would otherwise sit
    in the critical path of every approve/submit action.
    """
    from apps.accounts.models import User

    from .push import send_to_user

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return 0
    return send_to_user(
        user, title=title, body=body, url=url, notification_type=notification_type,
    )
