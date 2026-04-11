"""Pydantic v2 input schemas for MCP tools.

All schemas live here so the tool modules stay small and so schemas are easy
to import from tests. Field names match the corresponding REST API payloads
where possible so Claude can learn them from either surface.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


ProjectStatus = Literal[
    "draft", "active", "in_progress", "in_review", "completed", "archived",
]
PaymentKind = Literal["required", "bounty"]


class ListProjectsIn(_Base):
    status: Optional[ProjectStatus] = None
    assigned_to_id: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)


class GetProjectIn(_Base):
    project_id: int


class NewMilestoneSkillTag(_Base):
    skill_id: int
    xp_amount: int = Field(default=15, ge=0)


class NewMilestone(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    bonus_amount: Optional[Decimal] = None
    skill_tags: list[NewMilestoneSkillTag] = Field(default_factory=list)


class NewProjectSkillTag(_Base):
    skill_id: int
    xp_weight: int = Field(default=1, ge=1)


class CreateProjectIn(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    assigned_to_id: int
    difficulty: int = Field(default=1, ge=1, le=5)
    category_id: Optional[int] = None
    bonus_amount: Decimal = Decimal("0.00")
    payment_kind: PaymentKind = "required"
    materials_budget: Decimal = Decimal("0.00")
    hourly_rate_override: Optional[Decimal] = None
    due_date: Optional[date] = None
    status: ProjectStatus = "active"
    milestones: list[NewMilestone] = Field(default_factory=list)
    skill_tags: list[NewProjectSkillTag] = Field(default_factory=list)


class UpdateProjectStatusIn(_Base):
    project_id: int
    status: ProjectStatus


class CompleteMilestoneIn(_Base):
    milestone_id: int
    notes: str = ""


class SetProjectSkillTagsIn(_Base):
    project_id: int
    skill_tags: list[NewProjectSkillTag]


class MarkMaterialPurchasedIn(_Base):
    material_id: int
    actual_cost: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Rewards / Coins
# ---------------------------------------------------------------------------


class ListRewardsIn(_Base):
    active_only: bool = True


class GetCoinBalanceIn(_Base):
    user_id: Optional[int] = None


class RequestRedemptionIn(_Base):
    reward_id: int


class DecideRedemptionIn(_Base):
    redemption_id: int
    notes: str = ""


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


PaymentEntryType = Literal[
    "hourly", "project_bonus", "bounty_payout", "milestone_bonus",
    "materials_reimbursement", "payout", "adjustment",
]


class GetPaymentBalanceIn(_Base):
    user_id: Optional[int] = None


class ListPaymentLedgerIn(_Base):
    user_id: Optional[int] = None
    entry_type: Optional[PaymentEntryType] = None
    since: Optional[date] = None
    limit: int = Field(default=50, ge=1, le=500)


class RecordPayoutIn(_Base):
    user_id: int
    amount: Decimal = Field(gt=Decimal("0"))
    description: str = ""


class AdjustPaymentIn(_Base):
    user_id: int
    amount: Decimal
    description: str


# ---------------------------------------------------------------------------
# Timecards
# ---------------------------------------------------------------------------


TimeEntryStatus = Literal["active", "completed", "voided"]
TimecardStatus = Literal["pending", "approved", "paid", "disputed"]


class ListTimeEntriesIn(_Base):
    user_id: Optional[int] = None
    status: Optional[TimeEntryStatus] = None
    since: Optional[date] = None
    limit: int = Field(default=100, ge=1, le=500)


class GetActiveEntryIn(_Base):
    user_id: Optional[int] = None


class ListTimecardsIn(_Base):
    user_id: Optional[int] = None
    status: Optional[TimecardStatus] = None
    limit: int = Field(default=20, ge=1, le=100)


class ApproveTimecardIn(_Base):
    timecard_id: int
    notes: str = ""


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


BadgeRarity = Literal["common", "uncommon", "rare", "epic", "legendary"]


class ListSkillCategoriesIn(_Base):
    pass


class ListSkillsIn(_Base):
    category_id: Optional[int] = None
    subject_id: Optional[int] = None
    q: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=500)


class GetSkillTreeIn(_Base):
    category_id: int
    user_id: Optional[int] = None


class ListBadgesIn(_Base):
    rarity: Optional[BadgeRarity] = None


class ListEarnedBadgesIn(_Base):
    user_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


IngestionSourceType = Literal["instructables", "url", "pdf"]


class SubmitIngestionJobIn(_Base):
    source_type: IngestionSourceType
    source_url: str


class GetIngestionJobIn(_Base):
    job_id: str


class ListIngestionJobsIn(_Base):
    status: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class CommitIngestionJobIn(_Base):
    job_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    category_id: Optional[int] = None
    difficulty: Optional[int] = None
    bonus_amount: Optional[Decimal] = None
    materials_budget: Optional[Decimal] = None
    due_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Savings
# ---------------------------------------------------------------------------


class ListSavingsGoalsIn(_Base):
    user_id: Optional[int] = None
    include_completed: bool = False


class CreateSavingsGoalIn(_Base):
    title: str = Field(min_length=1, max_length=200)
    target_amount: Decimal = Field(gt=Decimal("0"))
    icon: str = ""


class ContributeToGoalIn(_Base):
    goal_id: int
    amount: Decimal = Field(gt=Decimal("0"))


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class ListProjectPhotosIn(_Base):
    project_id: int


class GetPortfolioSummaryIn(_Base):
    user_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class ListChildrenIn(_Base):
    pass


class GetUserIn(_Base):
    user_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class ListNotificationsIn(_Base):
    unread_only: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class MarkNotificationReadIn(_Base):
    notification_id: int


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class GetDashboardIn(_Base):
    user_id: Optional[int] = None
