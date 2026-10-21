"""Bounded inputs for saved reading history, corrections and removal."""
from datetime import date
from typing import ClassVar, Literal

from pydantic import Field, StrictInt, model_validator
from typing_extensions import TypedDict

from .reading_schemas import (
    MAX_DATABASE_ID, ReadingFormat, ReadingInterest, ReadingReaction,
    ReadingSessionOut, ReadingStatus, ReadingTargetIn,
)


class GetReadingBookIn(ReadingTargetIn):
    book_id: StrictInt = Field(ge=1, le=MAX_DATABASE_ID)


class GetReadingSessionIn(ReadingTargetIn):
    session_id: StrictInt = Field(ge=1, le=MAX_DATABASE_ID)


class ListReadingSessionsIn(ReadingTargetIn):
    book_id: StrictInt | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    since: date | None = Field(default=None, description="Include entries with occurred_on on or after this date.")
    until: date | None = Field(default=None, description="Include entries with occurred_on on or before this date.")
    limit: StrictInt = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("since must be on or before until.")
        return self


class _ReadingPatch(ReadingTargetIn):
    patch_fields: ClassVar[frozenset[str]]

    @model_validator(mode="before")
    @classmethod
    def reject_null_changes(cls, values):
        if isinstance(values, dict):
            for field in cls.patch_fields:
                if field in values and values[field] is None:
                    raise ValueError(f"{field} cannot be null; omit it to keep its saved value.")
        return values

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set & self.patch_fields:
            raise ValueError("Supply at least one field to change.")
        return self


class UpdateReadingBookIn(_ReadingPatch, GetReadingBookIn):
    patch_fields = frozenset({"title", "author", "status", "interests"})
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=160)
    status: ReadingStatus | None = None
    interests: list[ReadingInterest] | None = Field(default=None, max_length=6)


class UpdateReadingSessionIn(_ReadingPatch, GetReadingSessionIn):
    patch_fields = frozenset({
        "occurred_on", "duration_minutes", "pages_read", "section", "reflection", "format", "reaction",
    })
    occurred_on: date | None = None
    duration_minutes: StrictInt | None = Field(default=None, ge=0, le=600)
    pages_read: StrictInt | None = Field(default=None, ge=0, le=2000)
    section: str | None = Field(default=None, max_length=120)
    reflection: str | None = Field(default=None, max_length=3000)
    format: ReadingFormat | None = None
    reaction: ReadingReaction | None = None


class DeleteReadingBookIn(GetReadingBookIn):
    pass


class DeleteReadingSessionIn(GetReadingSessionIn):
    pass


class ListReadingSessionsOut(TypedDict):
    user_id: int
    sessions: list[ReadingSessionOut]
    total: int
    has_more: bool
    next_cursor: str | None


class DeleteReadingBookOut(TypedDict):
    deleted: Literal[True]
    book_id: int


class DeleteReadingSessionOut(TypedDict):
    deleted: Literal[True]
    session_id: int
