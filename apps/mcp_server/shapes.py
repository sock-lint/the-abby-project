"""Dict serializers for MCP tool outputs.

Where possible these reuse the existing DRF serializers so MCP output matches
the REST API byte-for-byte. Decimals and dates are coerced to JSON-safe types
(``str`` for Decimal to preserve precision, ISO-8601 for datetimes).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Primitive coercion
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def to_plain(data: Any) -> Any:
    """Recursively coerce serializer output to JSON-safe primitives."""
    return _json_safe(data)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def user_to_dict(user) -> dict[str, Any]:
    from apps.projects.serializers import UserSerializer

    return to_plain(UserSerializer(user).data)


def child_to_dict(user) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_label,
        "hourly_rate": str(user.hourly_rate),
        "avatar": user.avatar.url if user.avatar else None,
    }


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def project_list_to_dict(project) -> dict[str, Any]:
    from apps.projects.serializers import ProjectListSerializer

    return to_plain(ProjectListSerializer(project).data)


def project_detail_to_dict(project) -> dict[str, Any]:
    """Full project incl. milestones, materials, and skill tags."""
    from apps.projects.serializers import ProjectDetailSerializer

    data = to_plain(ProjectDetailSerializer(project).data)
    data["skill_tags"] = [
        {
            "skill_id": tag.skill_id,
            "skill_name": tag.skill.name,
            "xp_weight": tag.xp_weight,
        }
        for tag in project.skill_tags.select_related("skill").all()
    ]
    return data


def milestone_to_dict(milestone) -> dict[str, Any]:
    from apps.projects.serializers import ProjectMilestoneSerializer

    data = to_plain(ProjectMilestoneSerializer(milestone).data)
    data["skill_tags"] = [
        {
            "skill_id": tag.skill_id,
            "skill_name": tag.skill.name,
            "xp_amount": tag.xp_amount,
        }
        for tag in milestone.skill_tags.select_related("skill").all()
    ]
    return data


def material_to_dict(material) -> dict[str, Any]:
    from apps.projects.serializers import MaterialItemSerializer

    return to_plain(MaterialItemSerializer(material).data)


def savings_goal_to_dict(goal) -> dict[str, Any]:
    from apps.projects.serializers import SavingsGoalSerializer

    return to_plain(SavingsGoalSerializer(goal).data)


def notification_to_dict(notification) -> dict[str, Any]:
    from apps.notifications.serializers import NotificationSerializer

    return to_plain(NotificationSerializer(notification).data)


def ingestion_job_to_dict(job) -> dict[str, Any]:
    from apps.ingestion.serializers import ProjectIngestionJobSerializer

    return to_plain(ProjectIngestionJobSerializer(job).data)


def skill_category_to_dict(category) -> dict[str, Any]:
    from apps.projects.serializers import SkillCategorySerializer

    return to_plain(SkillCategorySerializer(category).data)


# ---------------------------------------------------------------------------
# Rewards / Coins
# ---------------------------------------------------------------------------


def reward_to_dict(reward) -> dict[str, Any]:
    from apps.rewards.serializers import RewardSerializer

    return to_plain(RewardSerializer(reward).data)


def redemption_to_dict(redemption) -> dict[str, Any]:
    from apps.rewards.serializers import RewardRedemptionSerializer

    return to_plain(RewardRedemptionSerializer(redemption).data)


def coin_ledger_entry_to_dict(entry) -> dict[str, Any]:
    from apps.rewards.serializers import CoinLedgerSerializer

    return to_plain(CoinLedgerSerializer(entry).data)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def payment_entry_to_dict(entry) -> dict[str, Any]:
    from apps.payments.serializers import PaymentLedgerSerializer

    return to_plain(PaymentLedgerSerializer(entry).data)


# ---------------------------------------------------------------------------
# Timecards
# ---------------------------------------------------------------------------


def time_entry_to_dict(entry) -> dict[str, Any]:
    from apps.timecards.serializers import TimeEntrySerializer

    return to_plain(TimeEntrySerializer(entry).data)


def timecard_to_dict(timecard) -> dict[str, Any]:
    from apps.timecards.serializers import TimecardSerializer

    return to_plain(TimecardSerializer(timecard).data)


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


def skill_to_dict(skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "icon": skill.icon,
        "category_id": skill.category_id,
        "category_name": skill.category.name if skill.category_id else None,
        "subject_id": skill.subject_id,
        "subject_name": skill.subject.name if skill.subject_id else None,
        "description": skill.description,
        "is_locked_by_default": skill.is_locked_by_default,
    }


def badge_to_dict(badge) -> dict[str, Any]:
    return {
        "id": badge.id,
        "name": badge.name,
        "description": badge.description,
        "icon": badge.icon,
        "rarity": badge.rarity,
        "xp_bonus": badge.xp_bonus,
        "criteria_type": badge.criteria_type,
        "criteria_value": badge.criteria_value,
        "subject_id": badge.subject_id,
    }


def user_badge_to_dict(user_badge) -> dict[str, Any]:
    return {
        "badge": badge_to_dict(user_badge.badge),
        "earned_at": user_badge.earned_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def project_photo_to_dict(photo) -> dict[str, Any]:
    from apps.portfolio.serializers import ProjectPhotoSerializer

    return to_plain(ProjectPhotoSerializer(photo).data)


# ---------------------------------------------------------------------------
# Chores
# ---------------------------------------------------------------------------


def chore_to_dict(chore) -> dict[str, Any]:
    from apps.chores.serializers import ChoreSerializer

    return to_plain(ChoreSerializer(chore).data)


def chore_completion_to_dict(completion) -> dict[str, Any]:
    from apps.chores.serializers import ChoreCompletionSerializer

    return to_plain(ChoreCompletionSerializer(completion).data)


def homework_assignment_to_dict(assignment) -> dict[str, Any]:
    from apps.homework.serializers import HomeworkAssignmentSerializer

    return to_plain(HomeworkAssignmentSerializer(assignment).data)


def homework_submission_to_dict(submission) -> dict[str, Any]:
    from apps.homework.serializers import HomeworkSubmissionSerializer

    return to_plain(HomeworkSubmissionSerializer(submission).data)


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def many(items: Iterable[Any], mapper) -> list[dict[str, Any]]:
    return [mapper(item) for item in items]
