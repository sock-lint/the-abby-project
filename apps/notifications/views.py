from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import NotificationType
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
