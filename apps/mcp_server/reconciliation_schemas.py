"""Strict inputs and global-only results for native challenge reconciliation."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from typing_extensions import TypedDict

from .schemas import _Base


MAX_ID = 9223372036854775807


class PreviewChallengeReconciliationIn(_Base):
    source_definition_id: StrictInt = Field(ge=1, le=MAX_ID)
    canonical_definition_id: StrictInt = Field(ge=1, le=MAX_ID)
    client_request_id: UUID

    @model_validator(mode="after")
    def distinct_definitions(self):
        if self.source_definition_id == self.canonical_definition_id:
            raise ValueError("Choose different source and canonical definitions.")
        return self


class GetChallengeReconciliationIn(_Base):
    preview_id: UUID


class PublishChallengeReconciliationIn(GetChallengeReconciliationIn):
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_cooperative_transition: StrictBool = False


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReconciliationFilterOut(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid", strict=True)

    allowed_triggers: list[str]
    skill_category_id: int
    on_time: bool


class ReconciliationRewardOut(ReconciliationResult):
    item_id: int
    quantity: int


class ReconciliationSkillOut(ReconciliationResult):
    skill_id: int
    xp_weight: int


class ReconciliationDefinitionOut(ReconciliationResult):
    id: int
    name: str
    description: str
    icon: str
    sprite_key: str
    quest_type: Literal["boss", "collection"]
    target_value: int
    duration_days: int | None
    trigger_filter: ReconciliationFilterOut
    required_badge_id: int | None
    prerequisite_quest_id: int | None
    required_skill_id: int | None
    required_skill_level: int
    coin_reward: int
    xp_reward: int
    is_repeatable: bool
    is_cooperative: bool
    is_system: bool
    superseded_by_id: int | None
    reward_items: list[ReconciliationRewardOut]
    skill_tags: list[ReconciliationSkillOut]
    creator_provenance: Literal["same_family_parent", "creatorless_global"]


class ReconciliationDifferenceOut(ReconciliationResult):
    field: Literal["is_cooperative"]
    source: bool
    canonical: bool


class ChallengeReconciliationOut(ReconciliationResult):
    preview_id: str
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    state_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_at: str
    published_at: str | None
    source_definition: ReconciliationDefinitionOut
    canonical_definition: ReconciliationDefinitionOut
    differences: list[ReconciliationDifferenceOut]
    requires_cooperative_acknowledgement: bool
    preservation: list[str]
    acknowledged_cooperative_transition: bool
