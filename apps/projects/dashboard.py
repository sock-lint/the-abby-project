"""Dashboard payload assembly — extracted from ``DashboardView.get``.

Audit H1: the inline view function had grown to ~145 lines with mixed
per-role concerns and a per-habit N+1 loop. Split into pure functions
that return JSON-ready dicts; the view becomes a thin dispatcher.

Each builder takes a User and returns the dict that goes straight
into ``Response(...)``. Imports stay lazy at the function level so
this module doesn't pull in the world at app-startup time.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone


def build_dashboard(user) -> dict[str, Any]:
    """Top-level dispatcher — assembles the per-role payload.

    Returns the dict the view sends back as JSON. Field ordering is
    arbitrary; the frontend reads by key.
    """
    today = timezone.localdate()
    payload = _common_dashboard(user, today)
    if user.role == "child":
        payload.update(_child_extras(user, today))
    elif user.role == "parent":
        payload.update(_parent_extras(user))
    payload["rpg"] = _rpg_block(user, today)
    payload["next_actions"] = _next_actions(user)
    return payload


# ---------------------------------------------------------------------------
# Shared between child + parent dashboards
# ---------------------------------------------------------------------------

def _common_dashboard(user, today) -> dict[str, Any]:
    from apps.lorebook.services import newly_unlocked_entries
    from apps.payments.services import PaymentService
    from apps.projects.models import Project, SavingsGoal
    from apps.projects.serializers import ProjectListSerializer, SavingsGoalSerializer
    from apps.rewards.services import CoinService
    from apps.timecards.models import TimeEntry
    from apps.timecards.services import ClockService, TimeEntryService

    active_entry = ClockService.get_active_entry(user)
    active_timer = None
    if active_entry:
        elapsed = (timezone.now() - active_entry.clock_in).total_seconds() / 60
        active_timer = {
            "project_id": active_entry.project_id,
            "project_title": active_entry.project.title,
            "clock_in": active_entry.clock_in.isoformat(),
            "elapsed_minutes": round(elapsed),
        }

    week_start = today - timedelta(days=today.weekday())
    week_entries = TimeEntry.objects.filter(
        user=user, status="completed",
        clock_in__date__gte=week_start,
    )
    week_aggregate = week_entries.aggregate(
        minutes=Sum("duration_minutes"),
        projects=Count("project", distinct=True),
    )
    week_minutes = week_aggregate["minutes"] or 0
    week_hours = round(week_minutes / 60, 1)

    active_projects = ProjectListSerializer(
        Project.objects.filter(
            assigned_to=user, status__in=["active", "in_progress"],
        )[:5],
        many=True,
    ).data

    return {
        "role": user.role,
        "active_timer": active_timer,
        "current_balance": float(PaymentService.get_balance(user)),
        "coin_balance": CoinService.get_balance(user),
        "this_week": {
            "hours_worked": week_hours,
            "earnings": float(week_hours * float(user.hourly_rate)),
            "projects_worked_on": week_aggregate["projects"] or 0,
        },
        "active_projects": active_projects,
        "recent_badges": _recent_badges(user),
        "streak_days": TimeEntryService.current_streak(user),
        "savings_goals": SavingsGoalSerializer(
            SavingsGoal.objects.filter(user=user, is_completed=False)[:3],
            many=True,
        ).data,
        "newly_unlocked_lorebook": (
            newly_unlocked_entries(user) if user.role == "child" else []
        ),
    }


def _recent_badges(user) -> list[dict[str, Any]]:
    from apps.achievements.models import UserBadge
    return list(
        UserBadge.objects.filter(user=user)
        .select_related("badge")
        .order_by("-earned_at")[:5]
        .values("badge__id", "badge__name", "badge__icon", "earned_at")
    )


# ---------------------------------------------------------------------------
# Child-only fields
# ---------------------------------------------------------------------------

def _child_extras(user, today) -> dict[str, Any]:
    from apps.chores.services import ChoreService
    from apps.timecards.models import Timecard

    chores_today = []
    for c in ChoreService.get_available_chores(user):
        chores_today.append({
            "id": c.pk,
            "title": c.title,
            "icon": c.icon,
            "reward_amount": str(c.reward_amount),
            "coin_reward": c.coin_reward,
            "is_done": c.is_done_today,
            "status": c.today_completion_status,
        })

    return {
        "chores_today": chores_today,
        "pending_chore_approvals": 0,
        "pending_timecards": Timecard.objects.filter(
            user=user, status="pending",
        ).count(),
    }


# ---------------------------------------------------------------------------
# Parent-only fields
# ---------------------------------------------------------------------------

def _parent_extras(user) -> dict[str, Any]:
    from apps.chores.models import ChoreCompletion
    from apps.timecards.models import Timecard

    # Audit C3: family-scope every parent counter. The leak this prevents
    # is documented at ``apps/projects/views.py:DashboardView.get`` history.
    pending_timecards = Timecard.objects.filter(
        status="pending", user__family=user.family,
    ).count()
    pending_chore_approvals = ChoreCompletion.objects.filter(
        status=ChoreCompletion.Status.PENDING,
        user__family=user.family,
    ).count()

    return {
        "chores_today": [],
        "pending_chore_approvals": pending_chore_approvals,
        "pending_timecards": pending_timecards,
    }


# ---------------------------------------------------------------------------
# RPG block — character profile + per-day habit summary (shared by both roles)
# ---------------------------------------------------------------------------

def _rpg_block(user, today) -> dict[str, Any]:
    from apps.habits.models import Habit, HabitLog
    from apps.rpg.models import CharacterProfile

    rpg_profile, _ = CharacterProfile.objects.get_or_create(user=user)
    habits = list(
        Habit.objects.filter(user=user, is_active=True),
    )

    # Audit H1 — per-habit ``HabitLog.objects.filter(...).count()`` was an
    # N+1 against the dashboard's hottest endpoint. One aggregated query
    # collapses N habit-count queries into 1.
    tap_counts: dict[int, int] = {}
    if habits:
        rows = (
            HabitLog.objects.filter(
                habit_id__in=[h.id for h in habits],
                user=user,
                direction=1,
                created_at__date=today,
            )
            .values("habit_id")
            .annotate(count=Count("id"))
        )
        tap_counts = {row["habit_id"]: row["count"] for row in rows}

    return {
        "level": rpg_profile.level,
        "login_streak": rpg_profile.login_streak,
        "longest_login_streak": rpg_profile.longest_login_streak,
        "perfect_days_count": rpg_profile.perfect_days_count,
        "last_active_date": rpg_profile.last_active_date,
        "habits_today": [
            {
                "id": h.pk,
                "name": h.name,
                "icon": h.icon,
                "habit_type": h.habit_type,
                "strength": h.strength,
                "taps_today": tap_counts.get(h.pk, 0),
                "max_taps_per_day": h.max_taps_per_day,
            }
            for h in habits
        ],
    }


# ---------------------------------------------------------------------------
# Next-actions feed (priority scorer)
# ---------------------------------------------------------------------------

def _next_actions(user) -> list[dict[str, Any]]:
    from apps.projects import priority as priority_module
    return [a.as_dict() for a in priority_module.build_next_actions(user)]
