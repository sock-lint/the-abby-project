"""Operational reading uses the same validation, writes and receipts as REST."""
from rest_framework.exceptions import NotFound, ValidationError

from apps.reading.models import ReadingBook
from apps.reading.serializers import (
    ReadingBookCreateSerializer, ReadingBookSerializer,
    ReadingSessionCreateSerializer, ReadingSessionSerializer,
)
from apps.reading.services import (
    authorized_reading,
    create_reading_book as save_reading_book,
    create_reading_session as save_reading_session,
    reading_summary,
)

from ..context import get_current_user, resolve_child_in_family, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..reading_schemas import (
    CreateReadingBookIn, GetReadingSummaryIn, ListReadingBooksIn, ListReadingBooksOut,
    LogReadingSessionIn, ReadingBookOut, ReadingSessionOut, ReadingSummaryOut,
)
from ..server import tool
from ..shapes import to_plain


def _reading_target(user_id):
    actor = get_current_user()
    if actor.role == "parent":
        if user_id is None:
            raise MCPValidationError(
                "Choose a child in your family with user_id.",
                field_errors={"user_id": ["Choose a child in your family."]},
            )
        return actor, resolve_child_in_family(actor, user_id)
    if actor.role != "child":
        raise MCPPermissionDenied("Reading is available only for child accounts.")
    return actor, resolve_target_user(actor, user_id)


def _book_payload(book):
    # Keep shelf responses bounded to saved reading fields. Discovery catalog
    # metadata remains on its existing REST surface rather than repeated here.
    payload = to_plain(ReadingBookSerializer(book).data)
    payload.pop("catalog_entry", None)
    return payload


def _save_reading(params, serializer_class, save):
    actor, target = _reading_target(params.user_id)
    serializer = serializer_class(
        data=params.model_dump(mode="json", exclude_none=True),
        context={"target_user": target},
    )
    try:
        serializer.is_valid(raise_exception=True)
        record, _ = save(actor, target, serializer.validated_data)
    except NotFound as exc:
        raise MCPNotFoundError(str(exc.detail)) from None
    except ValidationError as exc:
        fields = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        raise MCPValidationError(
            str(exc.detail),
            code="idempotency_conflict" if "client_request_id" in fields else "invalid_request",
            field_errors=fields,
        ) from None
    return record


@tool()
@safe_tool
def list_reading_books(params: ListReadingBooksIn) -> ListReadingBooksOut:
    """Read one child's shelf in stable ID order; follow next_after for more.

    Parents must choose a same-family child. Children read only themselves.
    This read never logs reading, advances goals, or awards a reward.
    """
    actor, target = _reading_target(params.user_id)
    with authorized_reading(actor, target) as (_, target):
        queryset = ReadingBook.objects.filter(user=target, pk__gt=params.after)
        if params.status:
            queryset = queryset.filter(status=params.status)
        rows = list(queryset.order_by("pk")[:params.limit + 1])
        has_more = len(rows) > params.limit
        selected = rows[:params.limit]
        return {
            "user_id": target.pk, "books": [_book_payload(book) for book in selected],
            "next_after": selected[-1].pk if has_more else None, "has_more": has_more,
        }


@tool()
@safe_tool
def get_reading_summary(params: GetReadingSummaryIn) -> ReadingSummaryOut:
    """Read saved reading totals and today's actual Reading Adventure receipt."""
    actor, target = _reading_target(params.user_id)
    with authorized_reading(actor, target) as (_, target):
        return {"user_id": target.pk, **reading_summary(target)}


@tool()
@safe_tool
def create_reading_book(params: CreateReadingBookIn) -> ReadingBookOut:
    """Save a book on a child's shelf once using a stable client_request_id.

    Identical retries return the current saved book; conflicting UUID reuse
    fails. Saving a book records no reading and awards no XP or Coins.
    """
    return _book_payload(_save_reading(params, ReadingBookCreateSerializer, save_reading_book))


@tool()
@safe_tool
def log_reading_session(params: LogReadingSessionIn) -> ReadingSessionOut:
    """Log reading against the child's book using a stable client_request_id.

    Include minutes, pages, section, or reflection. Omit occurred_on for the
    family-local day. The shared reading service owns all daily reward limits;
    reading_reward reports only an actual saved award. Identical retries reuse
    the entry and cannot repeat its award. Reuse the UUID after a timeout.
    """
    session = _save_reading(params, ReadingSessionCreateSerializer, save_reading_session)
    return to_plain(ReadingSessionSerializer(session).data)
