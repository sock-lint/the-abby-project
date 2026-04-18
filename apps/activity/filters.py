"""Simple query-parameter filtering for ActivityEventViewSet.

The project does not install ``django-filter``, so we parse ``request.query_params``
directly. Supported filters:

* ``subject`` — child user id (numeric)
* ``actor`` — acting user id (numeric)
* ``category`` — one of ActivityEvent.Category values
* ``event_type`` — dotted slug (e.g. ``chore.approve``)
* ``since`` / ``until`` — ISO datetime (inclusive)
* ``correlation_id`` — UUID
"""

from uuid import UUID

from django.utils.dateparse import parse_datetime


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _uuid_or_none(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def apply_activity_filters(queryset, query_params):
    """Filter ``queryset`` by supported query-string keys. Unknown keys ignored."""
    subject = _int_or_none(query_params.get("subject"))
    if subject is not None:
        queryset = queryset.filter(subject_id=subject)

    actor = _int_or_none(query_params.get("actor"))
    if actor is not None:
        queryset = queryset.filter(actor_id=actor)

    category = query_params.get("category")
    if category:
        queryset = queryset.filter(category=category)

    event_type = query_params.get("event_type")
    if event_type:
        queryset = queryset.filter(event_type=event_type)

    since = parse_datetime(query_params.get("since") or "")
    if since:
        queryset = queryset.filter(occurred_at__gte=since)

    until = parse_datetime(query_params.get("until") or "")
    if until:
        queryset = queryset.filter(occurred_at__lte=until)

    correlation_id = _uuid_or_none(query_params.get("correlation_id"))
    if correlation_id is not None:
        queryset = queryset.filter(correlation_id=correlation_id)

    return queryset
