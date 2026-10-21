"""Bounded MCP inputs and explicit results for reviewed database content drafts."""
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from .schemas import _Base


MAX_ID = 9223372036854775807


class WorkbenchReferencesIn(_Base):
    section: Literal["items", "quests", "skills", "badges"] = "items"
    after: StrictInt = Field(default=0, ge=0, le=MAX_ID)
    limit: StrictInt = Field(default=50, ge=1, le=100)


class ListContentDraftsIn(_Base):
    after: UUID | None = None
    published: StrictBool | None = None
    limit: StrictInt = Field(default=30, ge=1, le=100)


class CreateContentDraftIn(_Base):
    name: str = Field(min_length=1, max_length=100)


class ContentDraftIn(_Base):
    draft_id: UUID


class ContentDraftRevisionIn(ContentDraftIn):
    revision: StrictInt = Field(ge=1, le=2147483647)


class DraftChange(_Base):
    section: Literal["items", "quests"]
    object_id: StrictInt | None = Field(default=None, ge=1, le=MAX_ID)
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    values: dict[str, Any]


class SaveContentDraftIn(ContentDraftRevisionIn):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    changes: list[DraftChange] = Field(max_length=100)

    @model_validator(mode="after")
    def bound_changes(self):
        encoded = json.dumps([row.model_dump() for row in self.changes], allow_nan=False)
        if len(encoded.encode()) > 200000:
            raise ValueError("A draft contains at most 200 KB of content.")
        return self


class ReviewedContentDraftIn(ContentDraftRevisionIn):
    preview_id: UUID


class SimulationIn(_Base):
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_config(self):
        from apps.rpg.progression import normalize_config
        if len(json.dumps(self.config, allow_nan=False).encode()) > 20000:
            raise ValueError("A simulation configuration contains at most 20 KB.")
        normalize_config(self.config)
        return self


class SimulateContentDraftIn(ReviewedContentDraftIn, SimulationIn):
    pass


class PublishContentDraftIn(ReviewedContentDraftIn):
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class EmptyWorkbenchIn(_Base):
    pass


class WorkbenchResult(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class DraftSummaryOut(WorkbenchResult):
    id: str
    name: str
    revision: int
    published_at: str | None
    updated_at: str


class ContentDraftOut(DraftSummaryOut):
    changes: list[dict[str, Any]]
    preview: dict[str, Any] | None
    simulation: dict[str, Any] | None


class ContentDraftListOut(WorkbenchResult):
    drafts: list[DraftSummaryOut]
    total: int
    has_more: bool
    next_after: str | None


class WorkbenchReferencesOut(WorkbenchResult):
    section: str
    results: list[dict[str, Any]]
    total: int
    after: int
    next_after: int | None
    rules: dict[str, Any]


class ProgressionMetadataOut(WorkbenchResult):
    schema_version: int
    defaults: dict[str, Any]
    limits: dict[str, Any]
    catalog: dict[str, Any]
    coverage: dict[str, Any]
    rules_fingerprint: str
    engine_version: str
    work_budget: dict[str, Any]


class ProgressionReportOut(WorkbenchResult):
    schema_version: int
    config: dict[str, Any]
    catalog: dict[str, Any]
    coverage: dict[str, Any]
    rules_fingerprint: str
    engine_version: str
    milestones: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    summary: dict[str, Any]
    flows: dict[str, Any]
    audit: list[dict[str, Any]]
    journey: dict[str, Any]


class ContentDraftComparisonOut(WorkbenchResult):
    baseline: ProgressionReportOut
    proposed: ProgressionReportOut
    preview_id: str
    revision: int
    simulation: dict[str, Any]
