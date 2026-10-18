"""Bounded briefs for an external asset-production pipeline."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssetUse(_Input):
    surface: Literal["inventory", "reward_shop", "challenges", "projects", "badges", "skills", "companions", "avatar", "lorebook"]
    content_ref: str = Field(min_length=1, max_length=200, description="Existing or proposed catalog key; this does not create or enable it.")
    placement: str = Field(min_length=1, max_length=500)
    player_purpose: str = Field(min_length=1, max_length=1000, description="What this helps the child recognize, do, or earn.")
    integration_notes: str = Field(min_length=1, max_length=2000, description="Renderer/binding work needed; describe acquisition/unlocks separately from artwork.")


class AssetRequirements(_Input):
    formats: list[Literal["png", "webp", "glb", "json"]] = Field(min_length=1, max_length=4)
    width_px: int | None = Field(default=None, ge=16, le=4096)
    height_px: int | None = Field(default=None, ge=16, le=4096)
    transparent_background: bool = False
    max_file_bytes: int = Field(ge=1024, le=50 * 1024 * 1024)
    max_triangles: int | None = Field(default=None, ge=1, le=300000)
    animations: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def coherent_dimensions(self):
        if (self.width_px is None) != (self.height_px is None):
            raise ValueError("Supply both image dimensions or neither.")
        if any(len(name) > 100 or not name.strip() for name in self.animations):
            raise ValueError("Animation names must be nonempty and at most 100 characters.")
        if len(set(self.formats)) != len(self.formats):
            raise ValueError("Output formats must be unique.")
        return self


class AssetBrief(_Input):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["icon", "illustration", "portrait", "sprite_sheet", "companion_model", "animation", "ui_decoration"]
    creative_brief: str = Field(min_length=1, max_length=6000)
    rationale: str = Field(min_length=1, max_length=2000)
    uses: list[AssetUse] = Field(min_length=1, max_length=12)
    requirements: AssetRequirements
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    license_requirements: str = Field(min_length=1, max_length=2000)
    existing_alternatives: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def bounded_lists(self):
        if self.kind in {"icon", "illustration", "portrait", "sprite_sheet", "ui_decoration"}:
            if self.requirements.width_px is None or not set(self.requirements.formats) & {"png", "webp"}:
                raise ValueError("Image briefs need dimensions and a PNG/WebP output.")
        if self.kind == "companion_model" and ("glb" not in self.requirements.formats or self.requirements.max_triangles is None):
            raise ValueError("Companion models need GLB output and an explicit triangle budget.")
        for value in self.acceptance_criteria + self.existing_alternatives:
            if not value.strip() or len(value) > 1000:
                raise ValueError("Criteria and alternatives must be nonempty and at most 1000 characters.")
        return self


class ProposeAssetIn(_Input):
    request_id: UUID
    brief: AssetBrief


class ListAssetProposalsIn(_Input):
    status: Literal["proposed", "ready", "delivered", "cancelled"] | None = None
    after_id: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=100)


class GetAssetProposalIn(_Input):
    proposal_id: int = Field(ge=1)


class InspectAssetProposalIn(GetAssetProposalIn):
    after_event_id: int = Field(default=0, ge=0)
    event_limit: int = Field(default=25, ge=1, le=50)


class UpdateAssetProposalIn(GetAssetProposalIn):
    expected_revision: int = Field(ge=1)
    brief: AssetBrief


class ReviewAssetProposalIn(GetAssetProposalIn):
    expected_revision: int = Field(ge=1)
    decision: Literal["ready", "cancelled"]
    notes: str = Field(min_length=1, max_length=2000)


class RecordAssetDeliveryIn(GetAssetProposalIn):
    expected_revision: int = Field(ge=1)
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$", description="Opaque external pipeline artifact ID; no credentials, local paths or signed URLs.")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notes: str = Field(min_length=1, max_length=2000)
