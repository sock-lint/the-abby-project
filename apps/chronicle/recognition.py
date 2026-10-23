"""Record firsts without replaying an accomplishment's activity or rewards."""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def record_firsts(user, trigger_type, context=None):
    """Persist every applicable first and notify only for newly saved entries."""
    from apps.chronicle.firsts import slugs_for
    from apps.chronicle.services import ChronicleService
    from apps.notifications.models import Notification, NotificationType

    results = []
    for event_slug, title, icon_slug in slugs_for(trigger_type, context or {}):
        entry = ChronicleService.record_first(
            user, event_slug=event_slug, title=title, icon_slug=icon_slug,
        )
        if entry is not None:
            Notification.objects.create(
                user=user, notification_type=NotificationType.CHRONICLE_FIRST_EVER,
                title=title, message=f"{title} — added to your Yearbook.",
            )
        results.append({"entry_id": entry.pk if entry is not None else None, "event_slug": event_slug})
    return results


def safe_record_firsts(user, trigger_type, context=None):
    """Isolate optional recognition from the source's already successful payout."""
    try:
        return record_firsts(user, trigger_type, context)
    except Exception:
        logger.exception(
            "Chronicle recognition failed for user_id=%s trigger=%s", user.pk, trigger_type,
        )
        return []
