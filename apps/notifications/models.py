from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel


class NotificationType(models.TextChoices):
    """Enum of all notification kinds.

    Previously nested inside ``Notification.NotificationType``. Promoted
    to a top-level ``TextChoices`` so call sites can import it directly
    without circular-import acrobatics. Values (the string keys) are
    unchanged from the nested version — no data migration needed.
    """

    TIMECARD_READY = "timecard_ready", "Timecard Ready"
    TIMECARD_APPROVED = "timecard_approved", "Timecard Approved"
    BADGE_EARNED = "badge_earned", "Badge Earned"
    PROJECT_APPROVED = "project_approved", "Project Approved"
    PROJECT_CHANGES = "project_changes", "Changes Requested"
    PAYOUT_RECORDED = "payout_recorded", "Payout Recorded"
    SKILL_UNLOCKED = "skill_unlocked", "Skill Unlocked"
    MILESTONE_COMPLETED = "milestone_completed", "Milestone Completed"
    REDEMPTION_REQUESTED = "redemption_requested", "Redemption Requested"
    CHORE_SUBMITTED = "chore_submitted", "Chore Submitted"
    CHORE_APPROVED = "chore_approved", "Chore Approved"
    CHORE_REJECTED = "chore_rejected", "Chore Rejected"
    EXCHANGE_REQUESTED = "exchange_requested", "Exchange Requested"
    EXCHANGE_APPROVED = "exchange_approved", "Exchange Approved"
    EXCHANGE_DENIED = "exchange_denied", "Exchange Denied"
    PROJECT_DUE_SOON = "project_due_soon", "Project Due Soon"
    CHORE_REMINDER = "chore_reminder", "Chore Reminder"
    APPROVAL_REMINDER = "approval_reminder", "Approval Reminder"
    HOMEWORK_CREATED = "homework_created", "Homework Created"
    HOMEWORK_SUBMITTED = "homework_submitted", "Homework Submitted"
    HOMEWORK_APPROVED = "homework_approved", "Homework Approved"
    HOMEWORK_REJECTED = "homework_rejected", "Homework Rejected"
    HOMEWORK_DUE_SOON = "homework_due_soon", "Homework Due Soon"
    STREAK_MILESTONE = "streak_milestone", "Streak Milestone"
    PERFECT_DAY = "perfect_day", "Perfect Day"
    DAILY_CHECK_IN = "daily_check_in", "Daily Check-In"
    SAVINGS_GOAL_COMPLETED = "savings_goal_completed", "Savings Goal Completed"
    BIRTHDAY             = "birthday",             "Birthday"
    CHRONICLE_FIRST_EVER = "chronicle_first_ever", "Chronicle — first ever"
    COMEBACK_SUGGESTED   = "comeback_suggested",   "Comeback Quest Suggested"
    CREATION_SUBMITTED   = "creation_submitted",   "Creation Submitted"
    CREATION_APPROVED    = "creation_approved",    "Creation Approved"
    CREATION_REJECTED    = "creation_rejected",    "Creation Rejected"
    CHORE_PROPOSED          = "chore_proposed",          "Duty Proposed"
    HABIT_PROPOSED          = "habit_proposed",          "Ritual Proposed"
    CHORE_PROPOSAL_APPROVED = "chore_proposal_approved", "Duty Proposal Approved"
    HABIT_PROPOSAL_APPROVED = "habit_proposal_approved", "Ritual Proposal Approved"
    CHORE_PROPOSAL_REJECTED = "chore_proposal_rejected", "Duty Proposal Rejected"
    HABIT_PROPOSAL_REJECTED = "habit_proposal_rejected", "Ritual Proposal Rejected"
    QUEST_COMPLETED         = "quest_completed",         "Quest Completed"
    DROP_RECEIVED           = "drop_received",           "Drop Received"
    PET_EVOLVED             = "pet_evolved",             "Pet Evolved"
    MOUNT_BRED              = "mount_bred",              "Mount Bred"
    LOW_REWARD_STOCK        = "low_reward_stock",        "Reward Stock Low"
    REWARD_RESTOCKED        = "reward_restocked",        "Reward Back In Stock"


class Notification(CreatedAtModel):
    # Kept as a class-level alias so legacy ``Notification.NotificationType.X``
    # references keep working during the transition (callers have been
    # migrated to the top-level ``NotificationType`` import, but third-party
    # tests or temporary scripts may still use the old form).
    NotificationType = NotificationType

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    notification_type = models.CharField(
        max_length=25, choices=NotificationType.choices
    )
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "projects_notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.title}"
