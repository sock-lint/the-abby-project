"""Unit tests for apps.projects.priority — pure scoring math + filter rules.

DB-touching helpers (`_available_chores`, `_eligible_homework`,
`_untapped_positive_habits`, `_login_streak`) are patched out so these tests
don't require a populated DB. End-to-end DB coverage lives in
test_priority_integration.py.
"""
import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from apps.projects.priority import (
    NextAction,
    SCORING_WEIGHTS,
    build_next_actions,
    _chore_actions,
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


def _make_chore(*, pk, title, recurrence, is_done=False, icon="",
                reward=Decimal("0.00"), coins=0, created_at=None):
    """Build a chore-shaped stand-in. The real Chore model has many more
    fields but `_chore_actions` only reads a handful."""
    return SimpleNamespace(
        pk=pk, title=title, icon=icon,
        reward_amount=reward, coin_reward=coins,
        recurrence=recurrence, is_done_today=is_done,
        # `created_at` is normally a datetime — expose `.date()` like Django does.
        created_at=SimpleNamespace(date=lambda cd=created_at: cd),
    )


class ChoreScoringTests(TestCase):
    @patch("apps.projects.priority._available_chores")
    def test_weekly_scores_by_weekday(self, mock_available):
        # Thursday = weekday 3 → 10 + 3·8 = 34
        thursday = datetime.date(2026, 4, 16)
        chore = _make_chore(pk=1, title="Clean Room", recurrence="weekly",
                            reward=Decimal("1.00"), coins=2)
        mock_available.return_value = [chore]
        actions = _chore_actions(_child(), thursday)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].score, 34)
        self.assertEqual(actions[0].kind, "chore")
        self.assertEqual(actions[0].title, "Clean Room")
        self.assertEqual(actions[0].reward, {"money": "1.00", "coins": 2})

    @patch("apps.projects.priority._available_chores")
    def test_weekly_monday_scores_10(self, mock_available):
        monday = datetime.date(2026, 4, 13)
        mock_available.return_value = [
            _make_chore(pk=1, title="X", recurrence="weekly")
        ]
        self.assertEqual(_chore_actions(_child(), monday)[0].score, 10)

    @patch("apps.projects.priority._available_chores")
    def test_weekly_sunday_scores_58(self, mock_available):
        sunday = datetime.date(2026, 4, 19)
        mock_available.return_value = [
            _make_chore(pk=1, title="X", recurrence="weekly")
        ]
        self.assertEqual(_chore_actions(_child(), sunday)[0].score, 58)

    @patch("apps.projects.priority._available_chores")
    def test_daily_scores_70(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Dishes", recurrence="daily")
        ]
        self.assertEqual(_chore_actions(_child(), today)[0].score, 70)

    @patch("apps.projects.priority._available_chores")
    def test_one_time_climbs_over_days(self, mock_available):
        today = datetime.date(2026, 4, 16)
        assigned = datetime.date(2026, 4, 11)  # 5 days ago
        mock_available.return_value = [
            _make_chore(pk=1, title="Organize garage",
                        recurrence="one_time", created_at=assigned)
        ]
        # 50 + 2·5 = 60
        self.assertEqual(_chore_actions(_child(), today)[0].score, 60)

    @patch("apps.projects.priority._available_chores")
    def test_done_today_filtered_out(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Dishes", recurrence="daily", is_done=True)
        ]
        self.assertEqual(_chore_actions(_child(), today), [])

    @patch("apps.projects.priority._available_chores")
    def test_reward_omitted_when_both_zero(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Free chore", recurrence="daily")
        ]
        self.assertIsNone(_chore_actions(_child(), today)[0].reward)


from apps.projects.priority import _homework_actions


def _make_homework(*, pk, title, due_date, subject="math"):
    return SimpleNamespace(
        pk=pk, title=title, due_date=due_date, subject=subject,
        get_subject_display=lambda: subject.title(),
    )


class HomeworkScoringTests(TestCase):
    @patch("apps.projects.priority._eligible_homework")
    def test_overdue_scales_with_days(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Reading",
                           due_date=datetime.date(2026, 4, 13))
        ]
        # 3 days overdue → 100 + 3·10 = 130
        actions = _homework_actions(_child(), today)
        self.assertEqual(actions[0].score, 130)
        self.assertEqual(actions[0].kind, "homework")

    @patch("apps.projects.priority._eligible_homework")
    def test_overdue_caps_at_200(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="R",
                           due_date=datetime.date(2026, 3, 1))
        ]
        # Way more than 10 days late → capped at 200
        self.assertEqual(_homework_actions(_child(), today)[0].score, 200)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_today_scores_90(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [_make_homework(pk=1, title="Math", due_date=today)]
        self.assertEqual(_homework_actions(_child(), today)[0].score, 90)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_tomorrow_scores_60(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 17))
        ]
        self.assertEqual(_homework_actions(_child(), today)[0].score, 60)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_this_week_scores_30(self, mock_hw):
        today = datetime.date(2026, 4, 16)  # Thursday
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 20))
        ]
        # 4 days out, within 7-day horizon, not tomorrow → 30
        self.assertEqual(_homework_actions(_child(), today)[0].score, 30)

    @patch("apps.projects.priority._eligible_homework")
    def test_beyond_7_days_not_scored(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 30))
        ]
        self.assertEqual(_homework_actions(_child(), today), [])

    @patch("apps.projects.priority._eligible_homework")
    def test_subtitle_formats_due_date_phrase(self, mock_hw):
        today = datetime.date(2026, 4, 16)

        mock_hw.return_value = [
            _make_homework(pk=1, title="A", due_date=datetime.date(2026, 4, 14))
        ]
        self.assertIn("overdue", _homework_actions(_child(), today)[0].subtitle)

        mock_hw.return_value = [_make_homework(pk=2, title="B", due_date=today)]
        self.assertIn("today", _homework_actions(_child(), today)[0].subtitle)

        mock_hw.return_value = [
            _make_homework(pk=3, title="C", due_date=datetime.date(2026, 4, 17))
        ]
        self.assertIn("tomorrow", _homework_actions(_child(), today)[0].subtitle)
