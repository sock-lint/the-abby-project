"""Badge criteria checkers.

Each checker is a pure function ``(user, criteria: dict) -> bool`` registered
against one ``Badge.CriteriaType`` value via the ``@criterion`` decorator. The
registry keeps ``BadgeService._check_criteria`` a one-line dispatch and makes
each criterion testable in isolation.

Checkers live here (rather than inline in ``services.py``) so adding a new
criterion type only touches one module.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Count, Sum

from .models import Badge, SkillProgress

_CRITERIA_CHECKERS = {}


def criterion(criteria_type):
    """Register a checker function for a ``Badge.CriteriaType`` value."""
    def wrap(fn):
        _CRITERIA_CHECKERS[criteria_type] = fn
        return fn
    return wrap


def check(user, badge):
    """Dispatch a badge to its registered checker. Returns False if unknown."""
    fn = _CRITERIA_CHECKERS.get(badge.criteria_type)
    if fn is None:
        return False
    return fn(user, badge.criteria_value or {})


# ---------------------------------------------------------------------------
# Time-tracking criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.FIRST_CLOCK_IN)
def _first_clock_in(user, _c):
    from apps.timecards.services import TimeEntryService
    return TimeEntryService.completed_entries(user).exists()


@criterion(Badge.CriteriaType.HOURS_WORKED)
def _hours_worked(user, c):
    from apps.timecards.services import TimeEntryService
    total = TimeEntryService.completed_entries(user).aggregate(
        total=Sum("duration_minutes")
    )["total"] or 0
    return (total / 60) >= c.get("hours", 0)


@criterion(Badge.CriteriaType.HOURS_IN_DAY)
def _hours_in_day(user, c):
    from apps.timecards.services import TimeEntryService
    target = c.get("hours", 4)
    return TimeEntryService.daily_minute_totals(user).filter(
        total__gte=target * 60
    ).exists()


@criterion(Badge.CriteriaType.DAYS_WORKED)
def _days_worked(user, c):
    from apps.timecards.services import TimeEntryService
    return len(TimeEntryService.distinct_days(user)) >= c.get("count", 5)


@criterion(Badge.CriteriaType.STREAK_DAYS)
def _streak_days(user, c):
    from apps.timecards.services import TimeEntryService
    return TimeEntryService.longest_streak_at_least(user, c.get("days", 7))


@criterion(Badge.CriteriaType.PERFECT_TIMECARD)
def _perfect_timecard(user, _c):
    return user.timecards.filter(status="approved").exists()


# ---------------------------------------------------------------------------
# Project criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.FIRST_PROJECT)
def _first_project(user, _c):
    return user.assigned_projects.filter(status="completed").exists()


@criterion(Badge.CriteriaType.PROJECTS_COMPLETED)
def _projects_completed(user, c):
    return user.assigned_projects.filter(status="completed").count() >= c.get("count", 1)


@criterion(Badge.CriteriaType.CATEGORY_PROJECTS)
def _category_projects(user, c):
    count = c.get("count", 3)
    category_count = c.get("categories")
    if category_count:
        cats = user.assigned_projects.filter(
            status="completed", category__isnull=False,
        ).values("category").annotate(n=Count("id")).filter(n__gte=1)
        return cats.count() >= category_count
    return user.assigned_projects.filter(
        status="completed", category__name__iexact=c.get("category"),
    ).count() >= count


@criterion(Badge.CriteriaType.MATERIALS_UNDER_BUDGET)
def _materials_under_budget(user, _c):
    from apps.projects.models import Project
    return Project.objects.filter(
        assigned_to=user, status="completed", materials_budget__gt=0,
    ).annotate(
        actual_total=Sum("materials__actual_cost")
    ).filter(
        actual_total__lt=models.F("materials_budget") * models.Value(Decimal("0.9"))
    ).exists()


# ---------------------------------------------------------------------------
# Skill criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.SKILL_LEVEL_REACHED)
def _skill_level_reached(user, c):
    return SkillProgress.objects.filter(
        user=user, level__gte=c.get("level", 2),
    ).count() >= c.get("count", 1)


@criterion(Badge.CriteriaType.SKILLS_UNLOCKED)
def _skills_unlocked(user, c):
    return SkillProgress.objects.filter(
        user=user, unlocked=True, skill__is_locked_by_default=True,
    ).count() >= c.get("count", 1)


@criterion(Badge.CriteriaType.SUBJECTS_COMPLETED)
def _subjects_completed(user, c):
    return SkillProgress.objects.filter(
        user=user,
        level__gte=c.get("min_level", 2),
        skill__subject__isnull=False,
    ).values("skill__subject").distinct().count() >= c.get("count", 1)


@criterion(Badge.CriteriaType.SKILL_CATEGORIES_BREADTH)
def _skill_categories_breadth(user, c):
    return SkillProgress.objects.filter(
        user=user, level__gte=c.get("min_level", 1),
    ).values("skill__category").distinct().count() >= c.get("categories", 4)


@criterion(Badge.CriteriaType.CROSS_CATEGORY_UNLOCK)
def _cross_category_unlock(user, _c):
    from apps.achievements.models import SkillPrerequisite
    unlocked_skills = SkillProgress.objects.filter(
        user=user, unlocked=True, skill__is_locked_by_default=True,
    ).values_list("skill_id", flat=True)
    return SkillPrerequisite.objects.filter(
        skill_id__in=unlocked_skills,
    ).exclude(
        required_skill__category=models.F("skill__category"),
    ).exists()


# ---------------------------------------------------------------------------
# Misc criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.PHOTOS_UPLOADED)
def _photos_uploaded(user, c):
    return user.photos.count() >= c.get("count", 10)


@criterion(Badge.CriteriaType.TOTAL_EARNED)
def _total_earned(user, c):
    from apps.payments.models import PaymentLedger
    total = PaymentLedger.objects.filter(
        user=user, amount__gt=0,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return total >= c.get("amount", 500)


@criterion(Badge.CriteriaType.TOTAL_COINS_EARNED)
def _total_coins_earned(user, c):
    """Sum lifetime positive coin earnings (ignores spends and refunds)."""
    from apps.rewards.models import CoinLedger
    total = CoinLedger.objects.filter(
        user=user, amount__gt=0,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return total >= c.get("amount", 500)


# ---------------------------------------------------------------------------
# Homework criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.HOMEWORK_PLANNED_AHEAD)
def _homework_planned_ahead(user, c):
    """Count assignments the child logged ≥N days before the due date.

    ``criteria_value`` shape::

        {"count": 5, "days_ahead": 2}  # defaults: count=3, days_ahead=2

    Counts only active (non-deleted) assignments assigned to the user where
    the creation date was at least ``days_ahead`` days before the due date.
    Assignment status doesn't matter — the signal we're rewarding is the
    planning, not the completion (which gets its own badge line).
    """
    from apps.homework.models import HomeworkAssignment

    target = int(c.get("count", 3))
    days_ahead = int(c.get("days_ahead", 2))
    rows = HomeworkAssignment.objects.filter(
        assigned_to=user, is_active=True,
    ).values_list("due_date", "created_at")
    qualifying = sum(
        1 for due, created in rows
        if (due - created.date()).days >= days_ahead
    )
    return qualifying >= target


@criterion(Badge.CriteriaType.HOMEWORK_ON_TIME_COUNT)
def _homework_on_time_count(user, c):
    """Count approved homework submissions that were early or on-time.

    ``criteria_value`` shape::

        {"count": 5}  # default: 5
    """
    from apps.homework.models import HomeworkSubmission

    target = int(c.get("count", 5))
    return HomeworkSubmission.objects.filter(
        user=user,
        status=HomeworkSubmission.Status.APPROVED,
        timeliness__in=[
            HomeworkSubmission.Timeliness.EARLY,
            HomeworkSubmission.Timeliness.ON_TIME,
        ],
    ).count() >= target


# ---------------------------------------------------------------------------
# Quest criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.QUEST_COMPLETED)
def _quest_completed(user, c):
    """Badge awarded when the user has completed a specific quest.

    ``criteria_value`` shape::

        {"quest_name": "Seven Nights of Stories"}

    We match on ``QuestDefinition.name`` rather than a slug because quest
    definitions are name-keyed in the loader (no slug field on the model).
    Accepts a list for multi-quest badges (any-of), e.g.::

        {"quest_names": ["Quest A", "Quest B"]}
    """
    from apps.quests.models import Quest

    names = c.get("quest_names")
    if names is None:
        name = c.get("quest_name")
        if not name:
            return False
        names = [name]

    return Quest.objects.filter(
        participants__user=user,
        status=Quest.Status.COMPLETED,
        definition__name__in=list(names),
    ).exists()
