"""Explicit household targets, bounded history and saved RPG management results."""
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from .output_schemas import HistoryPage, RedemptionResult, Result
from .schemas import _Base


PositiveID = Annotated[StrictInt, Field(ge=1, le=9223372036854775807)]
ExpeditionTier = Literal["short", "standard", "long"]
ExpeditionStatus = Literal["active", "claimed", "expired"]
RedemptionStatus = Literal["pending", "approved", "denied", "fulfilled", "canceled"]


class HouseholdTargetIn(_Base):
    user_id: PositiveID | None = Field(
        default=None,
        description="Parents must explicitly select a same-family child. Children may select only themselves.",
    )


class HistoryIn(HouseholdTargetIn):
    limit: StrictInt = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


class RetryChallengeIn(HouseholdTargetIn):
    challenge_id: str = Field(
        pattern=r"^goal:[1-9][0-9]{0,18}$", max_length=24,
        description="Exact saved goal:<occurrence ID> to retry; legacy challenges are not eligible.",
    )


class FutureSkillTagIn(_Base):
    skill_id: PositiveID
    xp_weight: StrictInt = Field(default=1, ge=1, le=5)


class FutureChallengeSetupIn(_Base):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    target: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=3)
    coin_reward: StrictInt | None = Field(default=None, ge=0, le=10000)
    xp_reward: StrictInt | None = Field(default=None, ge=0, le=10000)
    skill_tags: list[FutureSkillTagIn] | None = Field(default=None, max_length=3)


class UpdateChallengeScheduleIn(HouseholdTargetIn):
    goal_definition_id: PositiveID
    expected_revision: StrictInt = Field(ge=0)
    request_id: UUID = Field(description="Stable UUID for this exact reviewed schedule change; reuse on retries.")
    paused: StrictBool | None = None
    next_week: FutureChallengeSetupIn | None = None


class ListExpeditionsIn(HistoryIn):
    status: ExpeditionStatus | None = None
    ready_only: StrictBool = False


class GetExpeditionIn(HouseholdTargetIn):
    expedition_id: PositiveID


class StartExpeditionIn(HouseholdTargetIn):
    mount_id: PositiveID
    tier: ExpeditionTier
    request_id: UUID = Field(description="Stable UUID for this exact launch; identical retries reuse the frozen loot.")


class ClaimExpeditionIn(GetExpeditionIn):
    pass


class ListRewardRedemptionsIn(HistoryIn):
    status: RedemptionStatus | None = None


class GetRewardRedemptionIn(HouseholdTargetIn):
    redemption_id: PositiveID


class DeliverRewardRedemptionIn(GetRewardRedemptionIn):
    pass


class ChallengeAttemptResult(Result):
    id: str
    goal_definition_id: int
    status: str
    retry_of: str | None
    reward_receipt: dict[str, Any]


class FutureChallengeSetupResult(Result):
    starts_at: str
    paused: bool
    name: str
    description: str
    metric: str
    target: str
    unit: str
    trigger_type: str | None
    movement_type_id: int | None
    coin_reward: int
    xp_reward: int
    skill_tags: list[dict[str, int]]


class ChallengeScheduleResult(Result):
    revision: int
    paused: bool
    next_week: FutureChallengeSetupResult


class UpdateChallengeScheduleResult(Result):
    goal_definition_id: int
    schedule: ChallengeScheduleResult


class ExpeditionResult(Result):
    id: int
    mount_id: int
    tier: ExpeditionTier
    status: ExpeditionStatus
    started_at: str
    returns_at: str
    claimed_at: str | None
    is_ready: bool
    seconds_remaining: int
    species_name: str
    species_slug: str
    species_sprite_key: str
    species_icon: str
    potion_name: str
    potion_slug: str
    loot: dict[str, Any]


class ExpeditionPage(HistoryPage):
    user_id: int
    expeditions: list[ExpeditionResult]


class ExpeditionMountResult(Result):
    id: int
    species_name: str
    species_slug: str
    species_sprite_key: str
    species_icon: str
    potion_name: str
    potion_slug: str


class ClaimExpeditionResult(Result):
    expedition_id: int
    tier: ExpeditionTier
    coins_awarded: int
    items: list[dict[str, Any]]
    freshly_claimed: bool
    mount: ExpeditionMountResult


class HouseholdRedemptionResult(RedemptionResult):
    delivered_at: str | None
    delivered_by: int | None


class RewardRedemptionPage(HistoryPage):
    user_id: int
    redemptions: list[HouseholdRedemptionResult]
