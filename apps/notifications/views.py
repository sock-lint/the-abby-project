from django.conf import settings
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NotificationType, PushSubscription
from .push import push_enabled
from .serializers import NotificationSerializer

# Notification types that warrant a one-shot full-screen celebration on
# next app open. The frontend ``CelebrationModal`` renders these.
CELEBRATION_TYPES = (
    NotificationType.STREAK_MILESTONE,
    NotificationType.PERFECT_DAY,
)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    # Explicit even though it matches the project default — every other
    # viewset declares its own permission_classes, and queryset scoping
    # via ``request.user.notifications`` only works if there IS a user,
    # so make the auth requirement load-bearing here too.
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.notifications.all()

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = request.user.notifications.filter(is_read=False).count()
        return Response({"count": count})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["get"], url_path="pending-celebration")
    def pending_celebration(self, request):
        """Return the most recent unread celebration-worthy notification.

        Used by the frontend to surface a one-shot full-screen modal on
        next app open for streak milestones (3/7/14/30/60/100) and
        Perfect Day awards. Returns 204 when nothing is pending.

        Sister endpoint to ``/api/chronicle/pending-celebration/`` (which
        handles the BIRTHDAY chronicle entry); split because birthdays
        are chronicle rows with their own viewed_at lifecycle while
        streaks/perfect-days flow through the notifications system.
        """
        notification = (
            request.user.notifications
            .filter(is_read=False, notification_type__in=CELEBRATION_TYPES)
            .order_by("-created_at")
            .first()
        )
        if notification is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(NotificationSerializer(notification).data)


class PushConfigView(APIView):
    """GET /api/push/config/ — what the browser needs to subscribe.

    Returns the VAPID *public* key (safe to expose; it is the half a browser
    must pass to ``pushManager.subscribe``) and whether push is configured at
    all. With no keypair set the frontend hides the whole affordance rather
    than offering a button that cannot work.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        enabled = push_enabled()
        return Response({
            "enabled": enabled,
            "public_key": settings.VAPID_PUBLIC_KEY if enabled else "",
        })


class PushSubscribeView(APIView):
    """POST /api/push/subscribe/ — register this browser for push.

    Body is the browser's ``PushSubscription.toJSON()`` shape. Idempotent on
    ``endpoint``: re-subscribing the same browser (or a different family
    member signing in on a shared device) updates the row in place rather
    than accumulating duplicates that would double-notify.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not push_enabled():
            return Response(
                {"detail": "Push notifications are not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        endpoint = (request.data.get("endpoint") or "").strip()
        keys = request.data.get("keys") or {}
        p256dh = (keys.get("p256dh") or "").strip()
        auth = (keys.get("auth") or "").strip()

        if not (endpoint and p256dh and auth):
            return Response(
                {"detail": "endpoint and keys.p256dh / keys.auth are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            },
        )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    """POST /api/push/unsubscribe/ — drop this browser's registration.

    Self-scoped: a request can only delete a subscription belonging to the
    caller, so knowing another household's endpoint string doesn't let you
    silence their phone.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        endpoint = (request.data.get("endpoint") or "").strip()
        if not endpoint:
            return Response(
                {"detail": "endpoint is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint,
        ).delete()
        return Response({"ok": True, "removed": deleted})
