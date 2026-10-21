"""Bounded MCP inputs for modern, server-tracked challenge goals."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from .schemas import _Base


class GetVoyagerFeedbackIn(_Base):
    """The current household aggregate accepts no child, policy or date selector."""


class ListChallengesIn(_Base):
    user_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    include_legacy: bool = True


class ChallengeSkillTag(_Base):
    skill_id: int = Field(ge=1)
    xp_weight: int = Field(default=1, ge=1, le=5)


class PreviewChallengeGoalIn(_Base):
    user_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)
    trigger_type: Literal[
        "clock_out", "chore_complete", "homework_complete", "homework_created",
        "milestone_complete", "project_complete", "habit_log", "journal_entry",
        "creation_logged", "movement_session", "savings_goal_complete", "reading_logged",
    ]
    movement_type_id: int | None = Field(default=None, ge=1)
    metric: Literal["count", "minutes", "distance"]
    target: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    unit: Literal["actions", "minutes", "mi", "km"]
    period: Literal["this_week", "from_today", "custom"] = "this_week"
    start_date: date | None = None
    end_date: date | None = None
    repeat_weekly: bool = False
    coin_reward: int = Field(default=0, ge=0, le=10000)
    xp_reward: int = Field(default=0, ge=0, le=10000)
    skill_tags: list[ChallengeSkillTag] = Field(default_factory=list, max_length=3)


class CreateChallengeGoalIn(PreviewChallengeGoalIn):
    request_id: UUID = Field(description="Stable UUID for this exact creation request; reuse it for retries.")


class PinChallengeIn(_Base):
    user_id: int | None = Field(default=None, ge=1)
    challenge_id: str = Field(pattern=r"^(goal|legacy):[1-9][0-9]*$", max_length=64)
