"""Signed, caller-bound pagination for immutable creation-time history."""
from typing import Any

from django.core import signing
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .errors import MCPValidationError


CURSOR_SALT = "abby.mcp.created-history.v1"
CURSOR_MAX_AGE = 86400


def paginate_created_history(
    queryset, *, actor, tool: str, filters: dict[str, Any], limit: int, cursor: str | None,
) -> tuple[list, dict[str, Any]]:
    """Page an already-authorized queryset in descending (created_at, pk) order.

    The signed maximum PK excludes later inserts, including backdated rows.
    Every page reuses the caller's current authorization filters; a cursor is
    never authority to read rows. ``total`` counts the currently matching rows
    within that initial PK boundary, before applying the page position.
    """
    binding = {
        "tool": tool, "actor_id": actor.pk, "role": actor.role,
        "family_id": actor.family_id, "filters": filters,
    }
    before = None
    if cursor is not None:
        try:
            payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=CURSOR_MAX_AGE)
            if not isinstance(payload, dict) or payload.get("binding") != binding:
                raise ValueError
            maximum_id, before_id = payload["maximum_id"], payload["before_id"]
            before = parse_datetime(payload["before_time"])
            if (
                type(maximum_id) is not int or type(before_id) is not int
                or not 0 < before_id <= maximum_id
                or before is None or timezone.is_naive(before)
            ):
                raise ValueError
        except (signing.BadSignature, TypeError, ValueError, KeyError):
            raise MCPValidationError("Invalid, expired or differently scoped history cursor.") from None
    else:
        maximum_id = queryset.aggregate(value=Max("pk"))["value"] or 0

    snapshot = queryset.filter(pk__lte=maximum_id)
    total = snapshot.count()
    if before is not None:
        snapshot = snapshot.filter(Q(created_at__lt=before) | Q(created_at=before, pk__lt=before_id))
    rows = list(snapshot.order_by("-created_at", "-pk")[:limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        last = rows[-1]
        next_cursor = signing.dumps({
            "binding": binding, "maximum_id": maximum_id,
            "before_time": last.created_at.isoformat(), "before_id": last.pk,
        }, salt=CURSOR_SALT, compress=True)
    return rows, {"total": total, "has_more": has_more, "next_cursor": next_cursor}
