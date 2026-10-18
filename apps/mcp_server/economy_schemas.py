"""Bounded MCP inputs for factual audits and anonymous economy projections."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Weight = Annotated[int, Field(ge=1, le=10000, strict=True)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetEconomyRulesIn(_Input):
    pass


class ListCoinLedgerIn(_Input):
    user_id: int | None = None
    since: date | None = None
    until: date | None = None
    reason: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class GetEconomyAuditIn(_Input):
    user_id: int | None = None
    since: date | None = None
    until: date | None = None


class MovementScenario(_Input):
    duration_minutes: int = Field(ge=1, le=1440, strict=True)
    intensity: Literal["low", "medium", "high"] = "medium"
    xp_weights: list[Weight] = Field(default_factory=list, max_length=10, description="Anonymous assumed skill-tag weights; no tags means no distributed XP.")


class ChoreScenario(_Input):
    count: int = Field(default=1, ge=1, le=20, strict=True)
    coin_reward: int = Field(default=0, ge=0, le=10000, strict=True)
    xp_reward: int = Field(default=0, ge=0, le=10000, strict=True)
    xp_weights: list[Weight] = Field(default_factory=list, max_length=10)


class AssumedOneOffAward(_Input):
    kind: Literal["project", "milestone", "tracked_work", "automatic_challenge"]
    source_key: str = Field(min_length=1, max_length=80, description="Anonymous unique receipt identity, never a real account selector.")
    day: int = Field(ge=1, le=31, strict=True)
    coin_reward: int = Field(default=0, ge=0, le=100000, strict=True, description="Explicitly assumed unboosted configured reward, not computed from project difficulty or monetary bonuses.")
    xp_reward: int = Field(default=0, ge=0, le=100000, strict=True, description="Assumed XP pool; milestone uses the supplied already-distributed direct XP total without the AwardService boost.")
    xp_weights: list[Weight] = Field(default_factory=list, max_length=10)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440, strict=True, description="Tracked-work drop eligibility only; Coin/XP amounts remain explicitly supplied assumptions.")
    already_rewarded: bool = False
    qualifying_source_key: str | None = Field(default=None, min_length=1, max_length=80, description="Optional anonymous source identity whose saved activity conditionally completes this automatic goal; adds no second activity or drop.")

    @model_validator(mode="after")
    def source_fields(self):
        if (self.kind == "tracked_work") != (self.duration_minutes is not None):
            raise ValueError("duration_minutes is required only for tracked_work.")
        if self.kind == "milestone" and self.xp_weights:
            raise ValueError("Milestone XP is the explicitly supplied direct total; omit weighted-pool assumptions.")
        if self.kind != "automatic_challenge" and self.qualifying_source_key is not None:
            raise ValueError("Only an automatic challenge can reference a qualifying source.")
        return self


class EconomyScenario(_Input):
    label: str = Field(default="Scenario", min_length=1, max_length=80)
    days: int = Field(default=7, ge=1, le=31, strict=True)
    starting_streak: int = Field(default=0, ge=0, le=10000, strict=True)
    character_level: int = Field(default=0, ge=0, le=6, strict=True)
    initial_coins: int = Field(default=0, ge=0, le=10000000, strict=True)
    target_cost_coins: int | None = Field(default=None, ge=1, le=10000000, strict=True)
    reading_minutes_per_day: int = Field(default=0, ge=0, le=600, strict=True)
    movement_sessions_per_day: list[MovementScenario] = Field(default_factory=list, max_length=12)
    creations_per_day: int = Field(default=0, ge=0, le=20, strict=True)
    creation_secondary_skill: bool = False
    chores_per_day: list[ChoreScenario] = Field(default_factory=list, max_length=10)
    one_off_awards: list[AssumedOneOffAward] = Field(default_factory=list, max_length=64)
    xp_boost: bool = False
    coin_boost: bool = False
    drop_boost: bool = False

    @model_validator(mode="after")
    def unique_receipts(self):
        by_key = {award.source_key: award for award in self.one_off_awards}
        if len(by_key) != len(self.one_off_awards):
            raise ValueError("Each anonymous one-off source_key must be unique, including replays.")
        for award in self.one_off_awards:
            if award.day > self.days:
                raise ValueError("Every one-off award must fall within the modeled horizon.")
            if award.qualifying_source_key:
                source = by_key.get(award.qualifying_source_key)
                if source is None or source.kind == "automatic_challenge" or source.day > award.day or source.already_rewarded:
                    raise ValueError("A qualifying source must be a non-replayed activity within or before the goal's modeled award day.")
        return self


class PreviewEconomyScenarioIn(_Input):
    scenarios: list[EconomyScenario] = Field(min_length=1, max_length=4)
