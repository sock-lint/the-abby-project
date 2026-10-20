"""Saved reading history and shared-service corrections without new rewards."""
from apps.reading.models import ReadingBook, ReadingSession
from apps.reading.serializers import ReadingSessionSerializer
from apps.reading.services import (
    ReadingHistoryConflict,
    authorized_reading,
    delete_reading_book as remove_book,
    delete_reading_session as remove_session,
    update_reading_book as save_book,
    update_reading_session as save_session,
)

from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..pagination import paginate_created_history
from ..reading_maintenance_schemas import (
    DeleteReadingBookIn, DeleteReadingBookOut, DeleteReadingSessionIn, DeleteReadingSessionOut,
    GetReadingBookIn, GetReadingSessionIn, ListReadingSessionsIn, ListReadingSessionsOut,
    UpdateReadingBookIn, UpdateReadingSessionIn,
)
from ..reading_schemas import ReadingBookOut, ReadingSessionOut
from ..server import tool
from ..shapes import to_plain
from .reading import _book_payload, _reading_target


def _owned_records(model, actor, target):
    queryset = model.objects.filter(
        user_id=target.pk, user__role="child", user__family_id=actor.family_id,
    )
    if model is ReadingSession:
        queryset = queryset.select_related("book", "reading_daily_reward")
    return queryset


def _owned_record(model, actor, target, record_id):
    record = _owned_records(model, actor, target).filter(pk=record_id).first()
    if record is None:
        raise MCPNotFoundError("Reading record not found.")
    return record


def _patch_data(params):
    return params.model_dump(mode="json", exclude_unset=True, include=params.patch_fields)


@tool()
@safe_tool
def get_reading_book(params: GetReadingBookIn) -> ReadingBookOut:
    """Read one saved shelf book for the explicitly selected child or child self."""
    actor, target = _reading_target(params.user_id)
    with authorized_reading(actor, target) as (actor, target):
        return _book_payload(_owned_record(ReadingBook, actor, target, params.book_id))


@tool()
@safe_tool
def get_reading_session(params: GetReadingSessionIn) -> ReadingSessionOut:
    """Read a saved reading entry, including its reflection and actual receipt.

    Parents must select the same-family reader. Children read only their own
    history. This read never credits minutes or awards XP or Coins.
    """
    actor, target = _reading_target(params.user_id)
    with authorized_reading(actor, target) as (actor, target):
        session = _owned_record(ReadingSession, actor, target, params.session_id)
        return to_plain(ReadingSessionSerializer(session).data)


@tool()
@safe_tool
def list_reading_sessions(params: ListReadingSessionsIn) -> ListReadingSessionsOut:
    """Read a child's saved entries in newest-created order with signed pagination.

    since/until filter the inclusive reading date; book_id filters the child's
    shelf. Follow next_cursor with the same reader and filters. Later inserts
    are excluded from that traversal. Corrections and deletions remain visible
    in current results and totals; reading dates do not determine page order.
    """
    actor, target = _reading_target(params.user_id)
    with authorized_reading(actor, target) as (actor, target):
        queryset = _owned_records(ReadingSession, actor, target)
        if params.book_id is not None:
            _owned_record(ReadingBook, actor, target, params.book_id)
            queryset = queryset.filter(book_id=params.book_id)
        if params.since is not None:
            queryset = queryset.filter(occurred_on__gte=params.since)
        if params.until is not None:
            queryset = queryset.filter(occurred_on__lte=params.until)
        rows, page = paginate_created_history(
            queryset, actor=actor, tool="list_reading_sessions",
            filters={
                "user_id": target.pk, "book_id": params.book_id,
                "since": params.since.isoformat() if params.since is not None else None,
                "until": params.until.isoformat() if params.until is not None else None,
            },
            limit=params.limit, cursor=params.cursor,
        )
        return {"user_id": target.pk, "sessions": to_plain(ReadingSessionSerializer(rows, many=True).data), **page}


@tool()
@safe_tool
def update_reading_book(params: UpdateReadingBookIn) -> ReadingBookOut:
    """Correct saved shelf details or status after confirming the exact changes.

    Supply only fields to change; omitted fields remain saved. Owner and the
    original create UUID are immutable. Repeating the same patch is safe and
    awards no reward; an original create retry returns this corrected book.
    """
    actor, target = _reading_target(params.user_id)
    return _book_payload(save_book(actor, target, params.book_id, _patch_data(params)))


@tool()
@safe_tool
def update_reading_session(params: UpdateReadingSessionIn) -> ReadingSessionOut:
    """Correct saved reading details after confirming the entry and exact changes.

    Owner, book and original UUID cannot change. A correction changes history
    totals but never advances or revokes daily credit, XP or Coins. An original
    create retry returns the corrected entry. Omitted fields remain saved.
    """
    actor, target = _reading_target(params.user_id)
    session = save_session(actor, target, params.session_id, _patch_data(params))
    return to_plain(ReadingSessionSerializer(session).data)


@tool()
@safe_tool
def delete_reading_book(params: DeleteReadingBookIn) -> DeleteReadingBookOut:
    """Remove a confirmed shelf book only when it has no reading entries.

    Books with entries must stay on the shelf to preserve history; use a status
    such as paused instead. A repeated delete may report not_found.
    """
    actor, target = _reading_target(params.user_id)
    try:
        remove_book(actor, target, params.book_id)
    except ReadingHistoryConflict as exc:
        raise MCPValidationError(str(exc.detail), code="history_conflict") from None
    return {"deleted": True, "book_id": params.book_id}


@tool()
@safe_tool
def delete_reading_session(params: DeleteReadingSessionIn) -> DeleteReadingSessionOut:
    """Remove a confirmed reading entry while retaining original daily credit.

    History totals change, but earned XP, Coins and daily receipts stay saved.
    Reusing its original create UUID cannot earn again, even on a later day;
    it may recreate the history entry. A repeated delete may report not_found.
    """
    actor, target = _reading_target(params.user_id)
    remove_session(actor, target, params.session_id)
    return {"deleted": True, "session_id": params.session_id}
