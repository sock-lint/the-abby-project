"""Unit tests for apps.projects.priority — pure scoring math + filter rules.

DB-touching helpers (`_available_chores`, `_eligible_homework`,
`_untapped_positive_habits`, `_login_streak`) are patched out so these tests
don't require a populated DB. End-to-end DB coverage lives in
test_priority_integration.py.
"""
import datetime
from types import SimpleNamespace
from unittest import TestCase

from apps.projects.priority import (
    NextAction,
    SCORING_WEIGHTS,
    build_next_actions,
)


def _parent():
    return SimpleNamespace(role="parent", pk=1)


def _child():
    return SimpleNamespace(role="child", pk=2)


class ScaffoldTests(TestCase):
    def test_parent_returns_empty_list(self):
        self.assertEqual(build_next_actions(_parent()), [])

    def test_scoring_weights_dict_has_expected_keys(self):
        required = {
            "homework_overdue_base", "homework_overdue_per_day",
            "homework_overdue_cap", "homework_due_today",
            "homework_due_tomorrow", "homework_due_this_week",
            "chore_daily", "chore_one_time_base",
            "chore_one_time_per_day", "chore_weekly_base",
            "chore_weekly_per_day", "habit_streak_protection",
        }
        self.assertTrue(required <= set(SCORING_WEIGHTS.keys()))

    def test_nextaction_serializes_to_dict_with_iso_date(self):
        action = NextAction(
            kind="homework", id=42, title="Math workbook",
            subtitle="due tomorrow", score=60,
            due_at=datetime.date(2026, 4, 17),
            reward=None, icon="BookOpen", tone="royal",
            action_url="/homework",
        )
        d = action.as_dict()
        self.assertEqual(d["kind"], "homework")
        self.assertEqual(d["id"], 42)
        self.assertEqual(d["due_at"], "2026-04-17")
        self.assertEqual(d["score"], 60)

    def test_nextaction_serializes_none_due_at(self):
        action = NextAction(
            kind="chore", id=7, title="Clean Room", subtitle="duty · $1",
            score=34, due_at=None, reward={"money": "1.00", "coins": 2},
            icon="Sparkles", tone="moss", action_url="/chores",
        )
        self.assertIsNone(action.as_dict()["due_at"])
