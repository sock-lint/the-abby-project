"""Shared Chronicle read policy for REST and MCP callers."""
from django.db.models import Q

from config.viewsets import filter_queryset_by_role


def visible_chronicle_entries(user, queryset):
    """Keep parent manual memories private while retaining Family history."""
    queryset = filter_queryset_by_role(user, queryset, "user")
    if user.role == "parent":
        queryset = queryset.exclude(
            (
                Q(kind__in=("journal", "grade"), is_private=True)
                | Q(kind="daily_note")
                | Q(kind="manual", user__role="parent")
            ) & ~Q(user=user),
        )
    return queryset
