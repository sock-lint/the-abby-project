"""Revisioned, explicit archive/restore commands and compact operation receipts."""
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from .schemas import _Base


class ArchiveRevisionIn(_Base):
    revision: StrictInt = Field(ge=1, le=2147483647)
    is_archived: StrictBool
    request_id: UUID


class ArchiveDraftIn(ArchiveRevisionIn):
    draft_id: UUID


class ArchiveExperimentIn(ArchiveRevisionIn):
    experiment_id: UUID


class ArchiveOperationOut(_Base):
    is_archived: bool
    revision: int


class AuthoringArchiveOut(_Base):
    kind: Literal["content", "editorial", "experiment"]
    id: str
    is_archived: bool
    revision: int
    published_at: str | None
    request_id: str
    replayed: bool
    operation: ArchiveOperationOut
