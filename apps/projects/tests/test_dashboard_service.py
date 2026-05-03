"""Tests for ``apps.projects.dashboard`` — the service-layer split that
replaced the 145-line god-method ``DashboardView.get`` (audit H1).

The split itself doesn't change the API contract (existing
``test_dashboard_view.py`` covers that). This file focuses on:

  * The per-habit N+1 fix — exactly one query for habit-tap counts
    regardless of how many habits a user has.
  * Direct unit tests of ``build_dashboard`` so future contributors can
    iterate on payload assembly without spinning up a request.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.habits.models import Habit, HabitLog
from apps.projects.dashboard import build_dashboard
from apps.projects.models import User


class DashboardHabitTapsAggregationTests(TestCase):
    """Audit H1: per-habit ``HabitLog.objects.filter().count()`` was N+1.
    The aggregated query collapses N tap-count queries into 1.
    """

    def setUp(self):
        self.child = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )

    def _seed(self, n_habits, taps_per_habit):
        today = timezone.localdate()
        habits = []
        for i in range(n_habits):
            h = Habit.objects.create(
                user=self.child,
                created_by=self.parent,
                name=f"Habit {i}",
                icon="🪴",
                habit_type="positive",
                xp_reward=0,
                max_taps_per_day=5,
            )
            for _ in range(taps_per_habit):
                HabitLog.objects.create(
                    habit=h,
                    user=self.child,
                    direction=1,
                    streak_at_time=0,
                )
            habits.append(h)
        return habits, today

    def test_habit_tap_counts_use_single_aggregated_query(self):
        # Seed 5 habits with varying tap counts.
        self._seed(n_habits=5, taps_per_habit=3)

        # Wrap the build call so we can inspect SQL emissions for the
        # habit-tap subquery specifically. Pre-fix, this loop would emit
        # 5 separate ``SELECT COUNT(*) FROM habits_habitlog WHERE
        # habit_id = ?`` queries.
        with CaptureQueriesContext(connection) as ctx:
            payload = build_dashboard(self.child)

        # Look for habit-log count queries — Django uses lowercase
        # table names so this is case-insensitive enough.
        habit_count_queries = [
            q for q in ctx.captured_queries
            if "habits_habitlog" in q["sql"].lower()
        ]
        # Pre-fix this would have been at least 5 (one per habit).
        # Post-fix it's exactly 1: the aggregated GROUP BY.
        self.assertLessEqual(
            len(habit_count_queries), 1,
            f"Expected ≤1 HabitLog query; got {len(habit_count_queries)}: "
            f"{[q['sql'] for q in habit_count_queries]}",
        )

        # Sanity: the payload still has the right tap counts.
        habits_today = payload["rpg"]["habits_today"]
        self.assertEqual(len(habits_today), 5)
        for h in habits_today:
            self.assertEqual(h["taps_today"], 3)

    def test_habit_with_zero_taps_returns_zero_not_missing(self):
        # The aggregation only emits rows for habits that have at least
        # one tap; the dict-fallback in dashboard.py must default to 0
        # for habits with no taps today.
        self._seed(n_habits=2, taps_per_habit=0)

        payload = build_dashboard(self.child)

        habits_today = payload["rpg"]["habits_today"]
        self.assertEqual(len(habits_today), 2)
        for h in habits_today:
            self.assertEqual(h["taps_today"], 0)

    def test_yesterdays_taps_dont_count(self):
        # Tap counts are scoped to today (same-day) — yesterday's taps
        # must not bleed into today's count.
        habits, today = self._seed(n_habits=1, taps_per_habit=0)
        log = HabitLog.objects.create(
            habit=habits[0], user=self.child, direction=1, streak_at_time=0,
        )
        # Backdate one tap to yesterday.
        yesterday = timezone.now() - timedelta(days=1)
        HabitLog.objects.filter(pk=log.pk).update(created_at=yesterday)

        payload = build_dashboard(self.child)

        habits_today = payload["rpg"]["habits_today"]
        self.assertEqual(habits_today[0]["taps_today"], 0)


class BuildDashboardShapeTests(TestCase):
    """Smoke tests that the split builders preserve the documented
    payload shape — the frontend reads these keys, so a regression here
    is a UI break."""

    def setUp(self):
        self.child = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )

    def _required_keys(self):
        return {
            "role", "active_timer", "current_balance", "coin_balance",
            "this_week", "active_projects", "pending_timecards",
            "recent_badges", "streak_days", "savings_goals",
            "chores_today", "next_actions", "pending_chore_approvals",
            "rpg", "newly_unlocked_lorebook",
        }

    def test_child_payload_has_all_documented_keys(self):
        payload = build_dashboard(self.child)
        self.assertTrue(self._required_keys() <= set(payload.keys()))
        self.assertEqual(payload["role"], "child")
        # rpg block has its own contract.
        self.assertTrue(
            {"level", "login_streak", "habits_today"}
            <= set(payload["rpg"].keys()),
        )

    def test_parent_payload_has_all_documented_keys(self):
        payload = build_dashboard(self.parent)
        self.assertTrue(self._required_keys() <= set(payload.keys()))
        self.assertEqual(payload["role"], "parent")
        # Parent never gets newly_unlocked_lorebook entries.
        self.assertEqual(payload["newly_unlocked_lorebook"], [])
        # Parent's chores_today is always empty (the field is for the
        # child's "what's available now" summary, not for parents).
        self.assertEqual(payload["chores_today"], [])
