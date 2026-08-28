"""Web Push delivery for the family's phones.

The whole economy is kid-submits → parent-approves → kid-collects, but a
closed PWA is inert: homework proof sat unseen until someone happened to open
the app. This is the out-of-app channel that makes the loop move.

Design rules, in priority order:

1. **Never break a notification.** ``notify()`` creates the in-app row first
   and fans out to push second. Every failure here — missing keys, missing
   library, a dead endpoint, a push service having a bad day — is swallowed
   and logged. A kid must still see the bell even if nobody's phone buzzes.
2. **Inert without configuration.** No VAPID keypair means ``push_enabled()``
   is False, subscriptions are refused, and the fan-out returns immediately.
   A deployment that never sets the env vars behaves exactly as it did before
   push existed.
3. **Subscriptions are disposable.** A 404 or 410 from the push service means
   the browser threw the subscription away (uninstalled, permission revoked,
   site data cleared). We delete our row rather than retrying forever.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Push services reject oversized payloads; keep the body well under the 4KB
# ceiling since our copy is a title plus a sentence.
MAX_BODY_CHARS = 200

# The push service says the subscription is gone for good.
DEAD_SUBSCRIPTION_STATUSES = {404, 410}


def push_enabled() -> bool:
    """True when a VAPID keypair is configured AND pywebpush is installed."""
    if not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
        return False
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        logger.warning("VAPID keys are set but pywebpush is not installed")
        return False
    return True


def send_to_user(user, *, title, body="", url="", notification_type="") -> int:
    """Fan a notification out to every device this user has registered.

    Returns the number of devices that accepted it. Never raises — callers
    are notification paths where a push failure must not roll anything back.
    """
    if not push_enabled():
        return 0

    from .models import PushSubscription

    subscriptions = list(PushSubscription.objects.filter(user=user))
    if not subscriptions:
        return 0

    payload = json.dumps({
        "title": title,
        "body": (body or "")[:MAX_BODY_CHARS],
        "url": url or "/",
        "type": notification_type,
    })

    delivered = 0
    for subscription in subscriptions:
        if _send_one(subscription, payload):
            delivered += 1
    return delivered


def _send_one(subscription, payload: str) -> bool:
    """Deliver one payload. Prunes the row when the endpoint is dead."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            timeout=10,
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in DEAD_SUBSCRIPTION_STATUSES:
            # The browser dropped this subscription — stop trying forever.
            pk = subscription.pk  # delete() clears it; capture for the log
            subscription.delete()
            logger.info("Pruned dead push subscription %s", pk)
        else:
            logger.warning("Web push failed (status=%s): %s", status, exc)
        return False
    except Exception:  # noqa: BLE001 — a push must never break its caller
        logger.exception("Unexpected error sending web push")
        return False

    # Cheap liveness marker; useful when debugging "my phone stopped buzzing".
    subscription.last_success_at = timezone.now()
    subscription.save(update_fields=["last_success_at"])
    return True
