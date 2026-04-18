from rest_framework import viewsets
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated

from config.permissions import IsParent

from .filters import apply_activity_filters
from .models import ActivityEvent
from .serializers import ActivityEventSerializer


class ActivityCursorPagination(CursorPagination):
    """Cursor pagination ordered newest-first.

    Append-only high-volume feed: cursor paging avoids both the count-query
    cost of ``PageNumberPagination`` and the page-drift that otherwise
    happens when new events arrive during a user's scroll.
    """

    page_size = 50
    max_page_size = 200
    page_size_query_param = "page_size"
    ordering = ("-occurred_at", "-id")


class ActivityEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Parent-only activity log. Children receive 403 on every route here."""

    serializer_class = ActivityEventSerializer
    permission_classes = [IsAuthenticated, IsParent]
    pagination_class = ActivityCursorPagination

    def get_queryset(self):
        qs = ActivityEvent.objects.select_related(
            "actor", "subject", "target_ct",
        ).all()
        return apply_activity_filters(qs, self.request.query_params)
