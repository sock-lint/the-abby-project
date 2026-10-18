"""Inputs for reviewed pack publication; separate from legacy CRUD schemas."""
from typing import Optional
from uuid import UUID

from pydantic import Field

from .schemas import LoadContentPackIn as LegacyLoadContentPackIn, _Base


class PreviewContentPackIn(_Base):
    pack: str = Field(min_length=1, max_length=40)


class PublishContentPackIn(PreviewContentPackIn):
    preview_id: UUID
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class LoadContentPackIn(LegacyLoadContentPackIn):
    preview_id: Optional[UUID] = None
    content_digest: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
