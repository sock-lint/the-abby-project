"""Signed, caller-bound pagination for saved datetime history."""
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
    order_field: str = "created_at",
) -> tuple[list, dict[str, Any]]:
    """Page an authorized queryset in descending (trusted datetime field, pk) order.

    The signed maximum PK excludes later inserts, including backdated rows.
    Every page reuses the caller's current authorization filters; a cursor is
    never authority to read rows. ``total`` counts the currently matching rows
    within that initial PK boundary, before applying the page position.
    The order field is selected by server code, never from client arguments.
    """
    if order_field not in {"created_at", "starts_at", "start_date"}:
        raise ValueError("Unsupported history ordering.")
    binding = {
        "tool": tool, "actor_id": actor.pk, "role": actor.role,
        "family_id": actor.family_id, "filters": filters,
    }
    if order_field != "created_at":
        # Keep existing creation-history cursor bindings valid for their TTL.
        binding["order_field"] = order_field
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
        snapshot = snapshot.filter(Q(**{f"{order_field}__lt": before}) | Q(**{order_field: before, "pk__lt": before_id}))
    rows = list(snapshot.order_by(f"-{order_field}", "-pk")[:limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        last = rows[-1]
        next_cursor = signing.dumps({
            "binding": binding, "maximum_id": maximum_id,
            "before_time": getattr(last, order_field).isoformat(), "before_id": last.pk,
        }, salt=CURSOR_SALT, compress=True)
    return rows, {"total": total, "has_more": has_more, "next_cursor": next_cursor}
