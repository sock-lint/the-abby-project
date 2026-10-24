"""Private editorial revisions; only reviewed textual changes are publishable."""
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from .schemas import _Base


class EditorialSectionIn(_Base):
    section: Literal["lorebook", "affirmations"]


class CreateEditorialDraftIn(EditorialSectionIn):
    name: str = Field(min_length=1, max_length=100)


class EditorialDraftIn(_Base):
    draft_id: UUID


class EditorialRevisionIn(EditorialDraftIn):
    revision: int = Field(ge=1, strict=True)


class EditorialChange(_Base):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    values: dict


class SaveEditorialDraftIn(EditorialRevisionIn):
    changes: list[EditorialChange] = Field(min_length=1, max_length=100)


class PublishEditorialDraftIn(EditorialRevisionIn):
    preview_id: UUID
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ListEditorialDraftsIn(_Base):
    include_archived: StrictBool = False
    after: UUID | None = None
    limit: int = Field(default=30, ge=1, le=50)


class EditorialDraftResult(_Base):
    is_archived: bool
    id: UUID
    section: Literal["lorebook", "affirmations"]
    name: str
    revision: int
    changes: list[EditorialChange]
    preview: dict | None
    published_at: str | None


class EditorialDraftSummary(_Base):
    is_archived: bool
    updated_at: str
    id: UUID
    section: Literal["lorebook", "affirmations"]
    name: str
    revision: int
    published_at: str | None
    has_preview: bool


class EditorialDraftPage(_Base):
    total: int
    has_more: bool
    drafts: list[EditorialDraftSummary]
    next_after: UUID | None


class EditorialCatalogResult(_Base):
    section: Literal["lorebook", "affirmations"]
    entries: list[dict]
