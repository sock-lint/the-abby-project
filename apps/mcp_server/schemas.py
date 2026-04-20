"""Pydantic v2 input schemas for MCP tools.

All schemas live here so the tool modules stay small and so schemas are easy
to import from tests. Field names match the corresponding REST API payloads
where possible so Claude can learn them from either surface.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


ResourceType = Literal["link", "video", "doc", "image"]


class NewStep(_Base):
    """An ordered walkthrough instruction (not a payment milestone).

    Marked complete to signal progress; never awards XP, coins, or money.

    ``milestone_index`` (when set) is a 0-based index into the ``milestones``
    array on the same ``create_project`` call — the step is grouped under
    that milestone in the UI's Plan view. Leave as ``None`` for a loose /
    ungrouped step.
    """
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    milestone_index: Optional[int] = None


class NewResource(_Base):
    """A reference link attached to a project, or to a specific step.

    ``step_index`` is a 0-based index into the ``steps`` array on the same
    ``create_project`` call. Leave as ``None`` for a project-level reference
    shown on the project Overview.
    """
    title: str = ""
    url: str = Field(min_length=1, max_length=1000)
    resource_type: ResourceType = "link"
    order: int = 0
    step_index: Optional[int] = None


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
    # Walkthrough content. Projects created via MCP without an Instructables
    # URL should populate ``steps`` so the child has "do this next" guidance;
    # ``resources`` can attach per-step videos or project-level references.
    steps: list[NewStep] = Field(default_factory=list)
    resources: list[NewResource] = Field(default_factory=list)


class UpdateProjectStatusIn(_Base):
    project_id: int
    status: ProjectStatus


class CompleteMilestoneIn(_Base):
    milestone_id: int
    notes: str = ""


# --- Tier 1.1: Project editing + nested CRUD ------------------------------


class UpdateProjectIn(_Base):
    project_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    category_id: Optional[int] = None
    bonus_amount: Optional[Decimal] = None
    payment_kind: Optional[PaymentKind] = None
    materials_budget: Optional[Decimal] = None
    hourly_rate_override: Optional[Decimal] = None
    due_date: Optional[date] = None
    parent_notes: Optional[str] = None
    instructables_url: Optional[str] = None


class DeleteProjectIn(_Base):
    project_id: int


class ProjectActionIn(_Base):
    project_id: int


class RequestProjectChangesIn(_Base):
    project_id: int
    parent_notes: str = ""


class AddMilestoneIn(_Base):
    project_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    bonus_amount: Optional[Decimal] = None
    skill_tags: list[NewMilestoneSkillTag] = Field(default_factory=list)


class UpdateMilestoneIn(_Base):
    milestone_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    order: Optional[int] = None
    bonus_amount: Optional[Decimal] = None
    skill_tags: Optional[list[NewMilestoneSkillTag]] = None


class DeleteMilestoneIn(_Base):
    milestone_id: int


class AddStepIn(_Base):
    project_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    milestone_id: Optional[int] = None


class UpdateStepIn(_Base):
    step_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    order: Optional[int] = None
    milestone_id: Optional[int] = None
    clear_milestone: bool = Field(
        default=False,
        description="Set true to explicitly unset the step's milestone (pass "
                    "milestone_id=None). Needed because a null milestone_id "
                    "would otherwise be treated as 'don't change'.",
    )


class DeleteStepIn(_Base):
    step_id: int


class StepActionIn(_Base):
    step_id: int


class AddMaterialIn(_Base):
    project_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    estimated_cost: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))


class UpdateMaterialIn(_Base):
    material_id: int
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    estimated_cost: Optional[Decimal] = None
    actual_cost: Optional[Decimal] = None
    is_purchased: Optional[bool] = None


class DeleteMaterialIn(_Base):
    material_id: int


class AddResourceIn(_Base):
    project_id: int
    url: str = Field(min_length=1, max_length=1000)
    title: str = ""
    resource_type: ResourceType = "link"
    order: int = 0
    step_id: Optional[int] = None


class UpdateResourceIn(_Base):
    resource_id: int
    url: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    title: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    order: Optional[int] = None
    step_id: Optional[int] = None
    clear_step: bool = False


class DeleteResourceIn(_Base):
    resource_id: int


# --- Tier 1.2: Project templates ------------------------------------------


class TemplateMilestoneDraft(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    bonus_amount: Optional[Decimal] = None


class TemplateMaterialDraft(_Base):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    estimated_cost: Decimal = Decimal("0.00")


class TemplateStepDraft(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    order: int = 0
    milestone_index: Optional[int] = None


class TemplateResourceDraft(_Base):
    url: str = Field(min_length=1, max_length=1000)
    title: str = ""
    resource_type: ResourceType = "link"
    order: int = 0
    step_index: Optional[int] = None


class ListTemplatesIn(_Base):
    is_public_only: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class GetTemplateIn(_Base):
    template_id: int


class CreateTemplateIn(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructables_url: Optional[str] = None
    difficulty: int = Field(default=1, ge=1, le=5)
    category_id: Optional[int] = None
    bonus_amount: Decimal = Decimal("0.00")
    materials_budget: Decimal = Decimal("0.00")
    is_public: bool = False
    milestones: list[TemplateMilestoneDraft] = Field(default_factory=list)
    materials: list[TemplateMaterialDraft] = Field(default_factory=list)
    steps: list[TemplateStepDraft] = Field(default_factory=list)
    resources: list[TemplateResourceDraft] = Field(default_factory=list)


class UpdateTemplateIn(_Base):
    template_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    instructables_url: Optional[str] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    category_id: Optional[int] = None
    bonus_amount: Optional[Decimal] = None
    materials_budget: Optional[Decimal] = None
    is_public: Optional[bool] = None


class DeleteTemplateIn(_Base):
    template_id: int


class SaveProjectAsTemplateIn(_Base):
    project_id: int
    is_public: bool = False


class CreateProjectFromTemplateIn(_Base):
    template_id: int
    assigned_to_id: int
    title_override: Optional[str] = Field(
        default=None, min_length=1, max_length=200,
    )


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


# --- Tier 1.3: Reward shop CRUD -------------------------------------------


RewardFulfillmentKind = Literal["real_world", "digital_item", "both"]


class CreateRewardIn(_Base):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    icon: str = ""
    cost_coins: int = Field(ge=0)
    rarity: BadgeRarity = "common"
    stock: Optional[int] = Field(default=None, ge=0)
    requires_parent_approval: bool = True
    is_active: bool = True
    order: int = 0
    fulfillment_kind: RewardFulfillmentKind = "real_world"
    item_definition_slug: Optional[str] = Field(
        default=None,
        description="Optional RPG ItemDefinition slug. When set, approval "
                    "of this reward will credit one of this item to the "
                    "user's inventory.",
    )


class UpdateRewardIn(_Base):
    reward_id: int
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    cost_coins: Optional[int] = Field(default=None, ge=0)
    rarity: Optional[BadgeRarity] = None
    stock: Optional[int] = Field(default=None, ge=0)
    clear_stock: bool = Field(
        default=False,
        description="Set true to set stock to None (unlimited). Overrides "
                    "the stock field.",
    )
    requires_parent_approval: Optional[bool] = None
    is_active: Optional[bool] = None
    order: Optional[int] = None
    fulfillment_kind: Optional[RewardFulfillmentKind] = None
    item_definition_slug: Optional[str] = None
    clear_item_definition: bool = False


class DeleteRewardIn(_Base):
    reward_id: int


class AdjustCoinsIn(_Base):
    user_id: int
    amount: int = Field(
        description="Positive to grant coins, negative to revoke.",
    )
    description: str = Field(min_length=1, max_length=200)


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


# --- Tier 2.1: Skill tree taxonomy ---------------------------------------


BadgeCriteriaType = Literal[
    "projects_completed",
    "hours_worked",
    "category_projects",
    "streak_days",
    "first_project",
    "first_clock_in",
    "materials_under_budget",
    "perfect_timecard",
    "skill_level_reached",
    "skills_unlocked",
    "skill_categories_breadth",
    "subjects_completed",
    "hours_in_day",
    "photos_uploaded",
    "total_earned",
    "days_worked",
    "cross_category_unlock",
]


class CreateCategoryIn(_Base):
    name: str = Field(min_length=1, max_length=100)
    icon: str = ""
    color: str = Field(default="#D97706", pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str = ""


class UpdateCategoryIn(_Base):
    category_id: int
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    icon: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    description: Optional[str] = None


class DeleteCategoryIn(_Base):
    category_id: int


class CreateSubjectIn(_Base):
    category_id: int
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    icon: str = ""
    order: int = 0


class UpdateSubjectIn(_Base):
    subject_id: int
    category_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None


class DeleteSubjectIn(_Base):
    subject_id: int


class SkillPrereqDraft(_Base):
    required_skill_id: int
    required_level: int = Field(default=2, ge=1, le=6)


class CreateSkillIn(_Base):
    category_id: int
    subject_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    icon: str = ""
    level_names: dict = Field(default_factory=dict)
    is_locked_by_default: bool = False
    order: int = 0
    prerequisites: list[SkillPrereqDraft] = Field(default_factory=list)


class UpdateSkillIn(_Base):
    skill_id: int
    category_id: Optional[int] = None
    subject_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    level_names: Optional[dict] = None
    is_locked_by_default: Optional[bool] = None
    order: Optional[int] = None
    clear_subject: bool = False


class DeleteSkillIn(_Base):
    skill_id: int


class AddSkillPrerequisiteIn(_Base):
    skill_id: int
    required_skill_id: int
    required_level: int = Field(default=2, ge=1, le=6)


class RemoveSkillPrerequisiteIn(_Base):
    skill_id: int
    required_skill_id: int


class CreateBadgeIn(_Base):
    name: str = Field(min_length=1, max_length=100)
    description: str
    icon: str = ""
    subject_id: Optional[int] = None
    criteria_type: BadgeCriteriaType
    criteria_value: dict = Field(default_factory=dict)
    xp_bonus: int = Field(default=0, ge=0)
    rarity: BadgeRarity = "common"


class UpdateBadgeIn(_Base):
    badge_id: int
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    subject_id: Optional[int] = None
    clear_subject: bool = False
    criteria_type: Optional[BadgeCriteriaType] = None
    criteria_value: Optional[dict] = None
    xp_bonus: Optional[int] = Field(default=None, ge=0)
    rarity: Optional[BadgeRarity] = None


class DeleteBadgeIn(_Base):
    badge_id: int


# --- Tier 2.2: Quests -----------------------------------------------------


QuestType = Literal["boss", "collection"]


class ListQuestsIn(_Base):
    user_id: Optional[int] = None
    include_completed: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class GetQuestIn(_Base):
    quest_id: int


class ListQuestCatalogIn(_Base):
    quest_type: Optional[QuestType] = None


class CreateQuestDefinitionIn(_Base):
    name: str = Field(min_length=1, max_length=100)
    description: str
    icon: str = "⚔️"
    quest_type: QuestType
    target_value: int = Field(ge=1)
    duration_days: int = Field(default=7, ge=1, le=365)
    trigger_filter: dict = Field(default_factory=dict)
    coin_reward: int = Field(default=0, ge=0)
    xp_reward: int = Field(default=0, ge=0)
    is_repeatable: bool = False
    required_badge_id: Optional[int] = None
    assigned_to_id: Optional[int] = Field(
        default=None,
        description="If set, also auto-start a live Quest for this child.",
    )


class AssignQuestIn(_Base):
    definition_id: int
    user_id: int


class CancelQuestIn(_Base):
    quest_id: int


# --- Tier 2.3: Habits -----------------------------------------------------


HabitType = Literal["positive", "negative", "both"]


class ListHabitsIn(_Base):
    user_id: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)


class GetHabitIn(_Base):
    habit_id: int


class CreateHabitIn(_Base):
    name: str = Field(min_length=1, max_length=100)
    icon: str = ""
    habit_type: HabitType = "positive"
    xp_reward: int = Field(default=5, ge=0)
    max_taps_per_day: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Per-day cap on positive taps. Negative taps stay uncapped.",
    )
    user_id: Optional[int] = Field(
        default=None,
        description="Parent-only: assign to a specific child. Omit to assign "
                    "to self.",
    )


class UpdateHabitIn(_Base):
    habit_id: int
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    icon: Optional[str] = None
    habit_type: Optional[HabitType] = None
    xp_reward: Optional[int] = Field(default=None, ge=0)
    max_taps_per_day: Optional[int] = Field(default=None, ge=1, le=50)
    is_active: Optional[bool] = None


class DeleteHabitIn(_Base):
    habit_id: int


class LogHabitIn(_Base):
    habit_id: int
    amount: int = Field(
        default=1,
        description="+1 for positive tap, -1 for negative tap. Rejected if "
                    "the habit type doesn't allow the sign.",
    )


# --- Tier 3.1: Children & collaborators -----------------------------------


ChildTheme = Literal["default", "abby", "otto"]


class UpdateChildIn(_Base):
    user_id: int
    hourly_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    display_name: Optional[str] = Field(default=None, max_length=100)
    theme: Optional[ChildTheme] = None


class AddCollaboratorIn(_Base):
    project_id: int
    user_id: int
    pay_split_percent: int = Field(default=50, ge=0, le=100)


class RemoveCollaboratorIn(_Base):
    project_id: int
    user_id: int


# --- Tier 3.2: Savings goal update/delete ---------------------------------


class UpdateSavingsGoalIn(_Base):
    goal_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    target_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    icon: Optional[str] = None


class DeleteSavingsGoalIn(_Base):
    goal_id: int


# --- Tier 3.3: Portfolio enrichment ---------------------------------------


class ListPortfolioMediaIn(_Base):
    user_id: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)


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
# Chores
# ---------------------------------------------------------------------------


ChoreRecurrence = Literal["daily", "weekly", "one_time"]
ChoreWeekSchedule = Literal["every_week", "alternating"]
ChoreCompletionStatus = Literal["pending", "approved", "rejected"]


class ListChoresIn(_Base):
    assigned_to_id: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)


class GetChoreIn(_Base):
    chore_id: int


class CreateChoreIn(_Base):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    icon: str = ""
    reward_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    coin_reward: int = Field(default=0, ge=0)
    recurrence: ChoreRecurrence = "daily"
    week_schedule: ChoreWeekSchedule = "every_week"
    schedule_start_date: Optional[date] = None
    assigned_to_id: Optional[int] = None
    is_active: bool = True
    order: int = 0


class UpdateChoreIn(_Base):
    chore_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    reward_amount: Optional[Decimal] = None
    coin_reward: Optional[int] = None
    recurrence: Optional[ChoreRecurrence] = None
    week_schedule: Optional[ChoreWeekSchedule] = None
    schedule_start_date: Optional[date] = None
    assigned_to_id: Optional[int] = None
    is_active: Optional[bool] = None
    order: Optional[int] = None


class CompleteChoreIn(_Base):
    chore_id: int
    notes: str = ""


class ListChoreCompletionsIn(_Base):
    user_id: Optional[int] = None
    status: Optional[ChoreCompletionStatus] = None
    limit: int = Field(default=50, ge=1, le=200)


class DecideChoreCompletionIn(_Base):
    completion_id: int


# ---------------------------------------------------------------------------
# Homework
# ---------------------------------------------------------------------------

HomeworkSubject = Literal[
    "math", "reading", "writing", "science", "social_studies", "art", "music", "other",
]
HomeworkSubmissionStatus = Literal["pending", "approved", "rejected"]


class ListHomeworkIn(_Base):
    assigned_to_id: Optional[int] = None
    subject: Optional[HomeworkSubject] = None
    limit: int = Field(default=50, ge=1, le=200)


class GetHomeworkIn(_Base):
    assignment_id: int


class CreateHomeworkIn(_Base):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    subject: HomeworkSubject = "other"
    effort_level: int = Field(default=3, ge=1, le=5)
    due_date: date
    assigned_to_id: int
    notes: str = ""
    skill_tags: list[dict] = Field(
        default_factory=list,
        description='[{"skill_id": 1, "xp_amount": 15}, ...]',
    )


class SubmitHomeworkIn(_Base):
    assignment_id: int
    notes: str = ""


class ListHomeworkSubmissionsIn(_Base):
    user_id: Optional[int] = None
    status: Optional[HomeworkSubmissionStatus] = None
    limit: int = Field(default=50, ge=1, le=200)


class DecideHomeworkSubmissionIn(_Base):
    submission_id: int


class PlanHomeworkIn(_Base):
    assignment_id: int


# --- Tier 1.4: Homework update/delete/templates ---------------------------


class HomeworkSkillTagDraft(_Base):
    skill_id: int
    xp_amount: int = Field(default=15, ge=0)


class UpdateHomeworkIn(_Base):
    assignment_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject: Optional[HomeworkSubject] = None
    effort_level: Optional[int] = Field(default=None, ge=1, le=5)
    due_date: Optional[date] = None
    notes: Optional[str] = None


class DeleteHomeworkIn(_Base):
    assignment_id: int


class SetHomeworkSkillTagsIn(_Base):
    assignment_id: int
    skill_tags: list[HomeworkSkillTagDraft]


class ListHomeworkTemplatesIn(_Base):
    limit: int = Field(default=50, ge=1, le=200)


class GetHomeworkTemplateIn(_Base):
    template_id: int


class CreateHomeworkTemplateIn(_Base):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    subject: HomeworkSubject = "other"
    effort_level: int = Field(default=3, ge=1, le=5)
    skill_tags: list[HomeworkSkillTagDraft] = Field(default_factory=list)


class UpdateHomeworkTemplateIn(_Base):
    template_id: int
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject: Optional[HomeworkSubject] = None
    effort_level: Optional[int] = Field(default=None, ge=1, le=5)
    skill_tags: Optional[list[HomeworkSkillTagDraft]] = None


class DeleteHomeworkTemplateIn(_Base):
    template_id: int


class CreateHomeworkFromTemplateIn(_Base):
    template_id: int
    assigned_to_id: int
    due_date: date


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class GetDashboardIn(_Base):
    user_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Content Packs (RPG YAML authoring)
# ---------------------------------------------------------------------------
#
# Packs live under ``content/rpg/packs/<name>/`` and are loaded with the
# existing ``loadrpgcontent`` pipeline using ``namespace=<name>-``. The LLM
# authors YAML files in a pack, validates with a dry-run, then commits.
# Writes to ``content/rpg/initial/`` are blocked unconditionally.


PackFilename = Literal[
    "items.yaml",
    "drops.yaml",
    "quests.yaml",
    "badges.yaml",
    "pet_species.yaml",
    "potion_types.yaml",
    "skill_tree.yaml",
    "rewards.yaml",
]


class ListContentPacksIn(_Base):
    pass


class GetContentPackIn(_Base):
    pack: str = Field(min_length=1, max_length=40)


class ReadPackFileIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    filename: PackFilename


class WritePackFileIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    filename: PackFilename
    yaml_content: str = Field(max_length=200_000)


class DeletePackFileIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    filename: PackFilename


class DeleteContentPackIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    confirm: bool = Field(
        default=False,
        description="Must be true to actually delete the pack directory.",
    )


class ValidateContentPackIn(_Base):
    pack: str = Field(min_length=1, max_length=40)


class LoadContentPackIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    dry_run: bool = False


class PrunePackContentIn(_Base):
    pack: str = Field(min_length=1, max_length=40)
    dry_run: bool = Field(
        default=False,
        description="Report counts without deleting anything.",
    )


class ListRpgCatalogIn(_Base):
    """Filters for the RPG catalog read tool.

    Empty = return everything. Use ``item_type`` to narrow items, and
    ``trigger_type`` to narrow drop-table entries to one trigger.
    """
    item_type: Optional[str] = None
    trigger_type: Optional[str] = None
    limit_per_section: int = Field(default=200, ge=1, le=1000)


# ---------------------------------------------------------------------------
# Draft pack entries (merge-write helper over write_pack_file)
# ---------------------------------------------------------------------------


DraftPackFilename = Literal[
    "items.yaml",
    "pet_species.yaml",
    "potion_types.yaml",
    "badges.yaml",
    "quests.yaml",
    "rewards.yaml",
]


class DraftPackEntriesIn(_Base):
    """Merge a list of YAML entries into an existing pack file.

    For files whose top-level key is a list of rows (items, pet_species,
    potion_types, badges, quests, rewards), this tool parses the existing
    file, appends or replaces, dedupes by natural key, and writes the
    result back. Saves the LLM from hand-merging YAML.
    """
    pack: str = Field(min_length=1, max_length=40)
    filename: DraftPackFilename
    entries: list[dict] = Field(
        min_length=1,
        description="Ready-to-serialize entries matching the loader's schema.",
    )
    mode: Literal["append", "replace"] = "append"


# ---------------------------------------------------------------------------
# Sprite asset ingestion
# ---------------------------------------------------------------------------


_SPRITE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class SheetDecl(_Base):
    """Declaration of a spritesheet to register in the shared manifest."""
    id: str = Field(
        min_length=1, max_length=64, pattern=_SPRITE_ID_PATTERN,
        description="Logical id (lowercase, hyphens, digits).",
    )
    file: str = Field(
        min_length=1, max_length=500,
        description=(
            "Repo-relative path to the sheet PNG. Must live under "
            "``reward-icons/<pack>/`` or the pack's own ``sprites/`` dir."
        ),
    )
    tile_size: int = Field(gt=0, le=512)


class SpriteTileDecl(_Base):
    """Declaration of a sheet-tile sprite."""
    slug: str = Field(
        min_length=1, max_length=64, pattern=_SPRITE_ID_PATTERN,
    )
    sheet: str = Field(
        min_length=1, max_length=64, pattern=_SPRITE_ID_PATTERN,
        description="Must match the ``id`` of a sheet being registered or "
                    "already present in the manifest.",
    )
    col: int = Field(ge=0, le=1024)
    row: int = Field(ge=0, le=1024)


class SpriteLooseDecl(_Base):
    """Declaration of a loose-file sprite (standalone PNG, copied as-is)."""
    slug: str = Field(
        min_length=1, max_length=64, pattern=_SPRITE_ID_PATTERN,
    )
    file: str = Field(
        min_length=1, max_length=500,
        description=(
            "Repo-relative path to the PNG. Must live under the pack's own "
            "``content/rpg/packs/<pack>/sprites/`` dir."
        ),
    )


class RegisterSpriteAssetsIn(_Base):
    """Register sprite artwork for a content pack.

    Idempotent: re-registering the same slug updates the manifest entry
    and (if ``force=True``) re-slices the output PNG. Slugs listed here
    become available as ``sprite_key`` values in the pack's YAML files.
    """
    pack: str = Field(min_length=1, max_length=40)
    sheets: list[SheetDecl] = Field(
        default_factory=list,
        description="Spritesheets to register. Can be empty if every sprite "
                    "below is a loose file or references a sheet already in "
                    "the manifest.",
    )
    tiles: list[SpriteTileDecl] = Field(
        default_factory=list,
        description="Sheet-tile sprites to register.",
    )
    loose: list[SpriteLooseDecl] = Field(
        default_factory=list,
        description="Loose-file sprites to register.",
    )
    force: bool = Field(
        default=False,
        description="Re-slice and overwrite any existing output PNGs.",
    )


# ---------------------------------------------------------------------------
# Sprite authoring (chat-to-prod runtime sprites)
# ---------------------------------------------------------------------------

FrameLayout = Literal["horizontal", "vertical"]
SPRITE_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class RegisterSpriteIn(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
    image_b64: Optional[str] = Field(
        default=None,
        description="Base64-encoded PNG or WebP bytes. Exactly one of image_b64/image_url required.",
    )
    image_url: Optional[str] = Field(
        default=None,
        description="https URL to PNG/WebP. Exactly one of image_b64/image_url required.",
    )
    pack: str = Field(default="user-authored", max_length=40)
    frame_count: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=0, ge=0, le=30)
    frame_layout: FrameLayout = "horizontal"
    overwrite: bool = False


class AnimatedSpriteTileDecl(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
    col: int = Field(ge=0, le=1024)
    row: int = Field(ge=0, le=1024)
    frame_count: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=0, ge=0, le=30)
    pack: str = Field(default="user-authored", max_length=40)


class RegisterSpriteBatchIn(_Base):
    sheet_b64: Optional[str] = None
    sheet_url: Optional[str] = None
    tile_size: int = Field(ge=8, le=256)
    tiles: list[AnimatedSpriteTileDecl] = Field(min_length=1, max_length=200)
    overwrite: bool = False


class ListSpritesIn(_Base):
    pack: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=500)


class DeleteSpriteIn(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)


SPRITE_TILE_SIZES = (32, 64, 128)


class GenerateSpriteSheetIn(_Base):
    """Input to the ``generate_sprite_sheet`` MCP tool.

    Frame-count / fps cross-validation mirrors ``SpriteAsset.clean()`` so
    invalid combinations fail fast at pydantic construction, before the
    tool ever runs and before the Gemini SDK is loaded.
    """

    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
    prompt: str = Field(min_length=3, max_length=500)
    frame_count: int = Field(default=1, ge=1, le=8)
    tile_size: int = Field(default=64)
    fps: int = Field(default=0, ge=0, le=30)
    pack: str = Field(default="ai-generated", max_length=40)
    style_hint: str = Field(default="", max_length=200)
    overwrite: bool = False

    @field_validator("tile_size")
    @classmethod
    def _tile_size_in_scale(cls, v: int) -> int:
        if v not in SPRITE_TILE_SIZES:
            raise ValueError(f"tile_size must be one of {SPRITE_TILE_SIZES}")
        return v

    @model_validator(mode="after")
    def _frames_and_fps(self) -> "GenerateSpriteSheetIn":
        if self.frame_count == 1 and self.fps != 0:
            raise ValueError("static sprites (frame_count == 1) require fps == 0")
        if self.frame_count > 1 and self.fps < 1:
            raise ValueError("animated sprites (frame_count > 1) require fps >= 1")
        return self
