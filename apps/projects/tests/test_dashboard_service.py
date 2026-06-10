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
from decimal import Decimal

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.habits.models import Habit, HabitLog
from apps.projects.dashboard import build_dashboard
from apps.projects.models import User
from config.tests.factories import make_family


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
        # Per-kid week stats land for parents (empty list when no child
        # has clocked completed time this week).
        self.assertEqual(payload["this_week_by_kid"], [])

    def test_role_exclusive_keys(self):
        # since_last_visit is child-only; this_week_by_kid is parent-only.
        child_payload = build_dashboard(self.child)
        parent_payload = build_dashboard(self.parent)
        self.assertIn("since_last_visit", child_payload)
        self.assertNotIn("since_last_visit", parent_payload)
        self.assertIn("this_week_by_kid", parent_payload)
        self.assertNotIn("this_week_by_kid", child_payload)


class ParentWeekByKidTests(TestCase):
    """``this_week_by_kid`` — per-child completed hours + earnings for the
    current week. The frontend's "Week at a glance" block consumed this key
    from day one; the backend half is the 2026-06 fix."""

    def setUp(self):
        fam = make_family(
            "Glance",
            parents=[{"username": "p1"}],
            children=[
                {"username": "kid1", "hourly_rate": Decimal("10.00"),
                 "display_name": "Abby"},
                {"username": "kid2", "hourly_rate": Decimal("8.00")},
            ],
        )
        self.parent = fam.parents[0]
        self.kid1, self.kid2 = fam.children

    def _entry(self, user, minutes, *, status="completed", days_ago=0):
        from apps.projects.models import Project
        from apps.timecards.models import TimeEntry

        project, _ = Project.objects.get_or_create(
            title="Birdhouse", assigned_to=user,
            defaults={"created_by": self.parent},
        )
        clock_in = timezone.now() - timedelta(days=days_ago)
        entry = TimeEntry.objects.create(
            user=user, project=project, clock_in=clock_in, status=status,
        )
        # Bypass save()'s clock_out-driven duration recompute so tests can
        # pin exact minutes without minting clock_out timestamps.
        TimeEntry.objects.filter(pk=entry.pk).update(duration_minutes=minutes)
        return entry

    def test_week_rows_have_hours_and_earnings(self):
        self._entry(self.kid1, 90)
        payload = build_dashboard(self.parent)

        rows = payload["this_week_by_kid"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kid_id"], self.kid1.pk)
        self.assertEqual(rows[0]["name"], "Abby")
        self.assertEqual(rows[0]["hours"], 1.5)
        self.assertEqual(rows[0]["earnings"], 15.0)

    def test_kid_without_entries_is_excluded(self):
        self._entry(self.kid1, 60)
        payload = build_dashboard(self.parent)

        kid_ids = [r["kid_id"] for r in payload["this_week_by_kid"]]
        self.assertNotIn(self.kid2.pk, kid_ids)

    def test_active_entries_dont_count(self):
        self._entry(self.kid1, 60, status="active")
        payload = build_dashboard(self.parent)
        self.assertEqual(payload["this_week_by_kid"], [])

    def test_other_familys_children_are_excluded(self):
        other = make_family(
            "Elsewhere",
            parents=[{"username": "op"}],
            children=[{"username": "okid"}],
        )
        self._entry(other.children[0], 120)
        payload = build_dashboard(self.parent)
        self.assertEqual(payload["this_week_by_kid"], [])

    def test_minutes_aggregate_across_entries(self):
        self._entry(self.kid2, 30)
        self._entry(self.kid2, 30)
        payload = build_dashboard(self.parent)

        rows = payload["this_week_by_kid"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hours"], 1.0)
        self.assertEqual(rows[0]["earnings"], 8.0)


class SinceLastVisitTests(TestCase):
    """``since_last_visit`` — badges / coins / approvals earned in the gap
    between two dashboard fetches, plus the ``last_seen_at`` stamp."""

    def setUp(self):
        fam = make_family(
            "Visits",
            parents=[{"username": "p1"}],
            children=[{"username": "kid"}],
        )
        self.parent = fam.parents[0]
        self.child = fam.children[0]

    def test_first_visit_returns_none_and_stamps(self):
        self.assertIsNone(self.child.last_seen_at)
        payload = build_dashboard(self.child)

        self.assertIsNone(payload["since_last_visit"])
        self.child.refresh_from_db()
        self.assertIsNotNone(self.child.last_seen_at)

    def test_gap_activity_is_counted(self):
        from apps.achievements.models import Badge, UserBadge
        from apps.notifications.models import Notification, NotificationType
        from apps.rewards.models import CoinLedger

        last_seen = timezone.now() - timedelta(days=2)
        User.objects.filter(pk=self.child.pk).update(last_seen_at=last_seen)
        self.child.refresh_from_db()

        badge = Badge.objects.create(
            name="First Steps", description="d",
            criteria_type=Badge.CriteriaType.FIRST_PROJECT,
        )
        UserBadge.objects.create(user=self.child, badge=badge)
        CoinLedger.objects.create(
            user=self.child, amount=12, reason=CoinLedger.Reason.HOURLY,
        )
        # Spends must not subtract from the "earned while away" number.
        CoinLedger.objects.create(
            user=self.child, amount=-50, reason=CoinLedger.Reason.REDEMPTION,
        )
        Notification.objects.create(
            user=self.child, title="Chore approved",
            notification_type=NotificationType.CHORE_APPROVED,
        )
        # Non-approval notifications don't count as approvals.
        Notification.objects.create(
            user=self.child, title="Drop",
            notification_type=NotificationType.DROP_RECEIVED,
        )

        payload = build_dashboard(self.child)
        summary = payload["since_last_visit"]

        self.assertEqual(summary["badges_earned"], 1)
        self.assertEqual(summary["coins_earned"], 12)
        self.assertEqual(summary["approvals"], 1)
        self.assertEqual(summary["last_seen_at"], last_seen.isoformat())

    def test_activity_before_last_seen_is_excluded(self):
        from apps.notifications.models import Notification, NotificationType

        note = Notification.objects.create(
            user=self.child, title="Old approval",
            notification_type=NotificationType.HOMEWORK_APPROVED,
        )
        Notification.objects.filter(pk=note.pk).update(
            created_at=timezone.now() - timedelta(days=5),
        )
        User.objects.filter(pk=self.child.pk).update(
            last_seen_at=timezone.now() - timedelta(days=1),
        )
        self.child.refresh_from_db()

        payload = build_dashboard(self.child)
        self.assertEqual(payload["since_last_visit"]["approvals"], 0)

    def test_each_fetch_advances_the_stamp(self):
        build_dashboard(self.child)
        self.child.refresh_from_db()
        first = self.child.last_seen_at

        build_dashboard(self.child)
        self.child.refresh_from_db()
        self.assertGreater(self.child.last_seen_at, first)

    def test_parent_fetch_also_stamps(self):
        build_dashboard(self.parent)
        self.parent.refresh_from_db()
        self.assertIsNotNone(self.parent.last_seen_at)
