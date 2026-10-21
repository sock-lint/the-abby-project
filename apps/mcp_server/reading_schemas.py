"""Bounded reading inputs and concrete, JSON-safe result contracts."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt
from typing_extensions import TypedDict

from .schemas import _Base


ReadingStatus = Literal["want_to_read", "reading", "finished", "paused"]
ReadingFormat = Literal["print", "ebook", "audiobook"]
ReadingReaction = Literal["", "loved", "liked", "okay", "not_for_me"]
ReadingInterest = Literal[
    "adventure", "fantasy", "mystery", "animals",
    "friendship", "science", "history", "humor",
]
MAX_DATABASE_ID = 9223372036854775807


class ReadingTargetIn(_Base):
    user_id: StrictInt | None = Field(
        default=None, ge=1, le=MAX_DATABASE_ID,
        description="Parents must explicitly choose a same-family child; children may select only themselves.",
    )


class ListReadingBooksIn(ReadingTargetIn):
    status: ReadingStatus | None = None
    after: StrictInt = Field(default=0, ge=0, le=MAX_DATABASE_ID, description="Resume after the previous page's next_after ID.")
    limit: StrictInt = Field(default=50, ge=1, le=100)


class GetReadingSummaryIn(ReadingTargetIn):
    pass


class CreateReadingBookIn(ReadingTargetIn):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=160)
    status: ReadingStatus = "reading"
    interests: list[ReadingInterest] = Field(default_factory=list, max_length=6)
    client_request_id: UUID = Field(description="Stable UUID for this exact create request; reuse on retries.")


class LogReadingSessionIn(ReadingTargetIn):
    book: StrictInt = Field(ge=1, le=MAX_DATABASE_ID, description="Book ID from this child's reading shelf.")
    occurred_on: date | None = Field(default=None, description="Omit for the family's current local day; future dates are rejected.")
    duration_minutes: StrictInt = Field(default=0, ge=0, le=600)
    pages_read: StrictInt = Field(default=0, ge=0, le=2000)
    section: str = Field(default="", max_length=120)
    reflection: str = Field(default="", max_length=3000)
    format: ReadingFormat = "print"
    reaction: ReadingReaction = ""
    client_request_id: UUID = Field(description="Stable UUID for this exact reading entry; reuse on retries.")


class ReadingBookOut(TypedDict):
    id: int
    user: int
    title: str
    author: str
    status: ReadingStatus
    interests: list[ReadingInterest]
    client_request_id: str
    created_at: str
    updated_at: str


class ListReadingBooksOut(TypedDict):
    user_id: int
    books: list[ReadingBookOut]
    next_after: int | None
    has_more: bool


class ReadingRewardOut(TypedDict):
    day: str
    xp_awarded: int
    coins_awarded: int


class ReadingSessionOut(TypedDict):
    id: int
    user: int
    book: int
    book_title: str
    book_author: str
    occurred_on: str
    duration_minutes: int
    pages_read: int
    section: str
    reflection: str
    format: ReadingFormat
    reaction: ReadingReaction
    client_request_id: str
    created_at: str
    updated_at: str
    reading_reward: ReadingRewardOut | None


class ReadingAdventureOut(TypedDict):
    day: str
    target_minutes: int
    minutes_credited: int
    remaining_minutes: int
    earned: bool
    base_xp: int
    base_coins: int
    xp_awarded: int
    coins_awarded: int
    skill_name: str


class ReadingSummaryOut(TypedDict):
    user_id: int
    books_total: int
    books_finished: int
    sessions_total: int
    total_minutes: int
    total_pages: int
    today: str
    timezone: str
    reading_adventure: ReadingAdventureOut
