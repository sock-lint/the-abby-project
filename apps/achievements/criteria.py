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

    count = c.get("count")
    qs = Quest.objects.filter(
        participants__user=user,
        status=Quest.Status.COMPLETED,
    )
    if names:
        qs = qs.filter(definition__name__in=list(names))
    if count is not None:
        return qs.count() >= int(count)
    return qs.exists()


# ---------------------------------------------------------------------------
# Pets / mounts collection criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.PETS_HATCHED)
def _pets_hatched(user, c):
    from apps.pets.models import UserPet
    return UserPet.objects.filter(user=user).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.PET_SPECIES_OWNED)
def _pet_species_owned(user, c):
    from apps.pets.models import UserPet
    return UserPet.objects.filter(user=user).values(
        "species",
    ).distinct().count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.MOUNTS_EVOLVED)
def _mounts_evolved(user, c):
    from apps.pets.models import UserMount
    return UserMount.objects.filter(user=user).count() >= int(c.get("count", 1))


# ---------------------------------------------------------------------------
# Chore / milestone / savings-goal / bounty / reward criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.CHORE_COMPLETIONS)
def _chore_completions(user, c):
    from apps.chores.models import ChoreCompletion
    return ChoreCompletion.objects.filter(
        user=user,
        status=ChoreCompletion.Status.APPROVED,
    ).count() >= int(c.get("count", 10))


@criterion(Badge.CriteriaType.MILESTONES_COMPLETED)
def _milestones_completed(user, c):
    from apps.projects.models import Project, ProjectMilestone
    return ProjectMilestone.objects.filter(
        project__in=Project.objects.filter(assigned_to=user),
        completed_at__isnull=False,
    ).count() >= int(c.get("count", 5))


@criterion(Badge.CriteriaType.SAVINGS_GOAL_COMPLETED)
def _savings_goal_completed(user, c):
    from apps.projects.models import SavingsGoal
    return SavingsGoal.objects.filter(
        user=user,
        is_completed=True,
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.BOUNTY_COMPLETED)
def _bounty_completed(user, c):
    from apps.projects.models import Project
    return Project.objects.filter(
        assigned_to=user,
        payment_kind=Project.PaymentKind.BOUNTY,
        status=Project.Status.COMPLETED,
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.REWARD_REDEEMED)
def _reward_redeemed(user, c):
    from apps.rewards.models import RewardRedemption
    return RewardRedemption.objects.filter(
        user=user,
        status=RewardRedemption.Status.FULFILLED,
    ).count() >= int(c.get("count", 1))


# ---------------------------------------------------------------------------
# RPG / CharacterProfile criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.PERFECT_DAYS_COUNT)
def _perfect_days_count(user, c):
    from apps.rpg.models import CharacterProfile
    # Query via ORM rather than `user.character_profile` to avoid the
    # reverse OneToOne cache going stale after a direct profile.save().
    row = CharacterProfile.objects.filter(user=user).values(
        "perfect_days_count",
    ).first()
    if not row:
        return False
    return row["perfect_days_count"] >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.STREAK_FREEZE_USED)
def _streak_freeze_used(user, c):
    from apps.rpg.models import CharacterProfile
    row = CharacterProfile.objects.filter(user=user).values(
        "streak_freezes_used",
    ).first()
    if not row:
        return False
    return row["streak_freezes_used"] >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.HABIT_MAX_STRENGTH)
def _habit_max_strength(user, c):
    """Any habit at ≥ threshold strength means the child has kept it up."""
    from apps.habits.models import Habit
    threshold = int(c.get("strength", 7))
    return Habit.objects.filter(
        user=user, is_active=True, strength__gte=threshold,
    ).exists()


# ---------------------------------------------------------------------------
# Time-of-day + project-speed criteria (fixes for broken legacy badges)
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.EARLY_BIRD)
def _early_bird(user, c):
    """Child has clocked in before the cutoff hour at least once."""
    from apps.timecards.models import TimeEntry
    cutoff = int(c.get("hour", 8))
    return TimeEntry.objects.filter(
        user=user, clock_in__hour__lt=cutoff,
    ).exists()


@criterion(Badge.CriteriaType.LATE_NIGHT)
def _late_night(user, c):
    """Child has clocked in after the cutoff hour — complements Early Bird."""
    from apps.timecards.models import TimeEntry
    cutoff = int(c.get("hour", 21))
    return TimeEntry.objects.filter(
        user=user, clock_in__hour__gte=cutoff,
    ).exists()


@criterion(Badge.CriteriaType.FAST_PROJECT)
def _fast_project(user, c):
    """Completed a project within N days of creation. Replaces broken Speed Runner."""
    from datetime import timedelta
    from apps.projects.models import Project
    days = int(c.get("days", 3))
    for proj in Project.objects.filter(
        assigned_to=user, status=Project.Status.COMPLETED,
        completed_at__isnull=False,
    ).only("created_at", "completed_at"):
        if (proj.completed_at - proj.created_at) <= timedelta(days=days):
            return True
    return False


# ---------------------------------------------------------------------------
# Depth-in-one-dimension criteria (2026-04-22 review)
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.CATEGORY_MASTERY)
def _category_mastery(user, c):
    """Every unlocked-by-default skill in the category at or above ``min_level``.

    ``criteria_value`` shape::

        {"category": "Cooking", "min_level": 3}

    Locked-by-default skills (Driving, Martial Arts, Team Sports, etc.) are
    excluded from the requirement so age- or prereq-gated content doesn't
    trap the badge forever. Kids who DO unlock and level a gated skill still
    need it — a SkillProgress row only exists for skills they've engaged
    with, and gated skills that stay locked simply don't appear in the
    required set. Prior to 2026-04-22 this required every skill including
    locked-by-default, which made Life Skills and Physical effectively
    unreachable for younger children.
    """
    from apps.achievements.models import Skill, SkillCategory

    category_name = c.get("category")
    if not category_name:
        return False
    try:
        category = SkillCategory.objects.get(name=category_name)
    except SkillCategory.DoesNotExist:
        return False
    min_level = int(c.get("min_level", 3))
    required_skill_ids = set(
        Skill.objects.filter(
            category=category, is_locked_by_default=False,
        ).values_list("id", flat=True)
    )
    if not required_skill_ids:
        return False
    user_skill_ids = set(
        SkillProgress.objects.filter(
            user=user, skill_id__in=required_skill_ids, level__gte=min_level,
        ).values_list("skill_id", flat=True)
    )
    return required_skill_ids.issubset(user_skill_ids)


@criterion(Badge.CriteriaType.FULL_POTION_SHELF)
def _full_potion_shelf(user, _c):
    """Own at least one of every potion in the live catalog."""
    from apps.pets.models import PotionType
    from apps.rpg.models import UserInventory

    all_potion_slugs = set(
        PotionType.objects.values_list("slug", flat=True)
    )
    if not all_potion_slugs:
        return False
    owned_slugs = set(
        UserInventory.objects.filter(
            user=user, quantity__gte=1,
            item__potion_type__isnull=False,
        ).values_list("item__potion_type__slug", flat=True)
    )
    return all_potion_slugs.issubset(owned_slugs)


@criterion(Badge.CriteriaType.CONSUMABLE_VARIETY)
def _consumable_variety(user, c):
    """Distinct consumable effects the user has ever used."""
    from apps.rpg.models import CharacterProfile
    row = CharacterProfile.objects.filter(user=user).values(
        "consumable_effects_used",
    ).first()
    if not row:
        return False
    used = row["consumable_effects_used"] or []
    return len(set(used)) >= int(c.get("count", 5))


@criterion(Badge.CriteriaType.COINS_SPENT_LIFETIME)
def _coins_spent_lifetime(user, c):
    """Lifetime coins debited via redemption.

    Redemption entries are negative on CoinLedger. We sum absolute values of
    the negative REDEMPTION rows — refunds are separate ``refund`` entries
    and net them out naturally if we also include those as positives.
    """
    from apps.rewards.models import CoinLedger
    total_spent = abs(
        CoinLedger.objects.filter(
            user=user,
            reason=CoinLedger.Reason.REDEMPTION,
            amount__lt=0,
        ).aggregate(total=Sum("amount"))["total"] or 0
    )
    refunded = CoinLedger.objects.filter(
        user=user, reason=CoinLedger.Reason.REFUND, amount__gt=0,
    ).aggregate(total=Sum("amount"))["total"] or 0
    net_spent = total_spent - refunded
    return net_spent >= int(c.get("amount", 50))


@criterion(Badge.CriteriaType.GRADE_REACHED)
def _grade_reached(user, c):
    """Reached at least grade N (9-12) according to User.current_grade.

    Driven by ``User.grade_entry_year`` which the parent sets on the profile.
    Post-HS the property returns values above 12 — those still satisfy "reached
    grade 12" but we don't emit higher-tier badges beyond Senior.
    """
    grade = user.current_grade if hasattr(user, "current_grade") else None
    if grade is None:
        return False
    return grade >= int(c.get("grade", 9))


@criterion(Badge.CriteriaType.BIRTHDAYS_LOGGED)
def _birthdays_logged(user, c):
    """Count Chronicle BIRTHDAY entries (one per year celebrated in-app)."""
    from apps.chronicle.models import ChronicleEntry
    return ChronicleEntry.objects.filter(
        user=user, kind=ChronicleEntry.Kind.BIRTHDAY,
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.COSMETIC_FULL_SET)
def _cosmetic_full_set(user, _c):
    """All four cosmetic slots (frame/title/theme/pet accessory) populated.

    Each ``CharacterProfile`` holds nullable FKs — this checker just
    confirms every one is non-null. Unequipping any slot silently drops
    the achievement state (badges are one-shot so the badge itself stays
    earned after first award).
    """
    from apps.rpg.models import CharacterProfile
    row = CharacterProfile.objects.filter(user=user).values(
        "active_frame_id", "active_title_id",
        "active_theme_id", "active_pet_accessory_id",
    ).first()
    if not row:
        return False
    return all(row[k] is not None for k in (
        "active_frame_id", "active_title_id",
        "active_theme_id", "active_pet_accessory_id",
    ))


# ---------------------------------------------------------------------------
# 2026-04-23 content-review criteria
# ---------------------------------------------------------------------------

@criterion(Badge.CriteriaType.HABIT_TAPS_LIFETIME)
def _habit_taps_lifetime(user, c):
    """Cumulative positive (+1) habit taps across every habit the user owns.

    ``criteria_value`` shape::

        {"count": 100}  # default: 50

    Negative direction never counts — habits are "rituals", and we reward
    the doing, not the acknowledging of a slip.
    """
    from apps.habits.models import HabitLog
    target = int(c.get("count", 50))
    return HabitLog.objects.filter(
        user=user, direction=1,
    ).count() >= target


@criterion(Badge.CriteriaType.HABIT_COUNT_AT_STRENGTH)
def _habit_count_at_strength(user, c):
    """N distinct active habits currently at or above ``strength``.

    ``criteria_value`` shape::

        {"count": 3, "strength": 5}  # defaults: count=3, strength=5

    Rewards breadth + depth simultaneously — the opposite of ``Rooted``
    (one habit at +7) which only needs depth.
    """
    from apps.habits.models import Habit
    target = int(c.get("count", 3))
    threshold = int(c.get("strength", 5))
    return Habit.objects.filter(
        user=user, is_active=True, strength__gte=threshold,
    ).count() >= target


@criterion(Badge.CriteriaType.BADGES_EARNED_COUNT)
def _badges_earned_count(user, c):
    """Total distinct badges the user has earned (universal 'Collector' ladder).

    ``criteria_value`` shape::

        {"count": 25}  # default: 10

    ``UserBadge`` is unique on ``(user, badge)`` so ``.count()`` IS the
    distinct-badge count — no need to filter further.
    """
    from apps.achievements.models import UserBadge
    return UserBadge.objects.filter(user=user).count() >= int(c.get("count", 10))


@criterion(Badge.CriteriaType.CO_OP_PROJECT_COMPLETED)
def _co_op_project_completed(user, c):
    """Count of completed projects where the user is a collaborator.

    ``criteria_value`` shape::

        {"count": 1}  # default: 1 ("first co-op project")

    Counts via ``ProjectCollaborator`` rows referencing a completed project.
    A user who is assigned to a project (``assigned_to``) does NOT count
    here — that's what ``PROJECTS_COMPLETED`` is for. This is specifically
    for the "helped on someone else's project" signal.
    """
    from apps.projects.models import ProjectCollaborator
    return ProjectCollaborator.objects.filter(
        user=user, project__status="completed",
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.BOSS_QUESTS_COMPLETED)
def _boss_quests_completed(user, c):
    """Count completed quests where the definition is a boss quest.

    ``criteria_value`` shape::

        {"count": 5}  # default: 5
    """
    from apps.quests.models import Quest, QuestDefinition
    return Quest.objects.filter(
        participants__user=user,
        status=Quest.Status.COMPLETED,
        definition__quest_type=QuestDefinition.QuestType.BOSS,
    ).count() >= int(c.get("count", 5))


@criterion(Badge.CriteriaType.COLLECTION_QUESTS_COMPLETED)
def _collection_quests_completed(user, c):
    """Count completed quests where the definition is a collection quest.

    ``criteria_value`` shape::

        {"count": 5}  # default: 5
    """
    from apps.quests.models import Quest, QuestDefinition
    return Quest.objects.filter(
        participants__user=user,
        status=Quest.Status.COMPLETED,
        definition__quest_type=QuestDefinition.QuestType.COLLECTION,
    ).count() >= int(c.get("count", 5))


@criterion(Badge.CriteriaType.CHRONICLE_MILESTONES_LOGGED)
def _chronicle_milestones_logged(user, c):
    """Count chronicle milestone entries recorded for the user.

    ``criteria_value`` shape::

        {"count": 3}  # default: 3

    Distinct from ``BIRTHDAYS_LOGGED`` (which counts BIRTHDAY kind) — this
    is for ``MILESTONE`` kind only, which fires on graduation, first-ever
    events, etc.
    """
    from apps.chronicle.models import ChronicleEntry
    return ChronicleEntry.objects.filter(
        user=user, kind=ChronicleEntry.Kind.MILESTONE,
    ).count() >= int(c.get("count", 3))


@criterion(Badge.CriteriaType.JOURNAL_ENTRIES_WRITTEN)
def _journal_entries_written(user, c):
    """Lifetime count of child-authored Chronicle journal entries.

    ``criteria_value`` shape::

        {"count": 10}  # default: 1 (first-entry badge)
    """
    from apps.chronicle.models import ChronicleEntry
    return ChronicleEntry.objects.filter(
        user=user, kind=ChronicleEntry.Kind.JOURNAL,
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.JOURNAL_STREAK_DAYS)
def _journal_streak_days(user, c):
    """Longest run of consecutive local-days with at least one journal entry.

    ``criteria_value`` shape::

        {"days": 7}  # default: 3

    Multiple entries on the same day count as one calendar day.
    """
    from apps.chronicle.models import ChronicleEntry
    target = int(c.get("days", 3))
    days = sorted(
        {
            d
            for d in ChronicleEntry.objects.filter(
                user=user, kind=ChronicleEntry.Kind.JOURNAL,
            ).values_list("occurred_on", flat=True)
        }
    )
    if not days:
        return False
    best = 1
    run = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best >= target


@criterion(Badge.CriteriaType.CREATIONS_LOGGED)
def _creations_logged(user, c):
    """Lifetime count of Creations logged by this user.

    ``criteria_value`` shape::

        {"count": 10}  # default: 1 (first-spark badge)

    Counts every Creation row regardless of status — the proud-display track
    is the primary recognition. Approved-bonus tier has its own ladder.
    """
    from apps.creations.models import Creation
    return Creation.objects.filter(user=user).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.CREATIONS_APPROVED)
def _creations_approved(user, c):
    """Count of Creations whose parent bonus was APPROVED.

    ``criteria_value`` shape::

        {"count": 5}  # default: 1
    """
    from apps.creations.models import Creation
    return Creation.objects.filter(
        user=user, status=Creation.Status.APPROVED,
    ).count() >= int(c.get("count", 1))


@criterion(Badge.CriteriaType.CREATION_SKILL_BREADTH)
def _creation_skill_breadth(user, c):
    """Creations tagged across at least N distinct creative skills.

    Counts both primary and secondary skill tags — each distinct Skill a
    user has ever tagged any of their Creations with contributes to breadth.

    ``criteria_value`` shape::

        {"count": 5}  # default: 5 (Polymath)
    """
    from apps.creations.models import Creation
    target = int(c.get("count", 5))
    primary_ids = set(
        Creation.objects.filter(user=user).values_list("primary_skill_id", flat=True)
    )
    secondary_ids = set(
        Creation.objects.filter(
            user=user, secondary_skill__isnull=False,
        ).values_list("secondary_skill_id", flat=True)
    )
    return len(primary_ids | secondary_ids) >= target


@criterion(Badge.CriteriaType.COSMETIC_SET_OWNED)
def _cosmetic_set_owned(user, c):
    """Own every item in a specific named cosmetic set.

    ``criteria_value`` shape::

        {"slugs": ["frame-scholar", "title-scholar", "theme-library"]}

    The user must have a ``UserInventory`` row with ``quantity >= 1`` for
    every listed slug. Returns False if the list is empty or missing.
    """
    from apps.rpg.models import UserInventory
    slugs = c.get("slugs") or []
    if not slugs:
        return False
    owned = set(
        UserInventory.objects.filter(
            user=user, quantity__gte=1, item__slug__in=slugs,
        ).values_list("item__slug", flat=True)
    )
    return set(slugs).issubset(owned)
