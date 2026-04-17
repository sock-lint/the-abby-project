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


from apps.projects.priority import _habit_actions


def _make_habit(*, pk, name, strength=0, icon="", max_taps=1, taps_today=0,
                habit_type="positive"):
    return SimpleNamespace(
        pk=pk, name=name, strength=strength, icon=icon,
        habit_type=habit_type, max_taps_per_day=max_taps,
        _taps_today=taps_today,
    )


class HabitStreakProtectionTests(TestCase):
    def _patch(self, habits, streak):
        """Stack two patches as context managers and return their mocks
        for tests that don't need to assert on call args."""
        habits_patch = patch(
            "apps.projects.priority._untapped_positive_habits",
            return_value=list(habits),
        )
        streak_patch = patch(
            "apps.projects.priority._login_streak",
            return_value=streak,
        )
        habits_patch.start()
        streak_patch.start()
        self.addCleanup(habits_patch.stop)
        self.addCleanup(streak_patch.stop)

    def test_no_streak_returns_empty(self):
        self._patch([_make_habit(pk=1, name="Brush", strength=5)], streak=0)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19),
            [],
        )

    def test_early_hour_returns_empty(self):
        self._patch([_make_habit(pk=1, name="Brush", strength=5)], streak=3)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=17),
            [],
        )

    def test_streak_protection_scores_65(self):
        self._patch(
            [_make_habit(pk=1, name="Brush teeth", strength=5, icon="🪥")],
            streak=3,
        )
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].score, 65)
        self.assertEqual(actions[0].kind, "habit")
        self.assertEqual(actions[0].title, "Brush teeth")
        self.assertEqual(actions[0].tone, "ember")

    def test_picks_highest_strength(self):
        self._patch([
            _make_habit(pk=1, name="Aaa", strength=1),
            _make_habit(pk=2, name="Zzz", strength=10),
        ], streak=3)
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id, 2)  # the high-strength one

    def test_ties_break_alphabetically(self):
        self._patch([
            _make_habit(pk=1, name="Zebra", strength=5),
            _make_habit(pk=2, name="Apple", strength=5),
        ], streak=3)
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(actions[0].title, "Apple")

    def test_empty_list_returns_empty(self):
        self._patch([], streak=3)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19),
            [],
        )


class OrchestratorTests(TestCase):
    def _patch_all(self, *, chores=(), homework=(), habits=(), streak=0):
        for target, value in [
            ("apps.projects.priority._available_chores", list(chores)),
            ("apps.projects.priority._eligible_homework", list(homework)),
            ("apps.projects.priority._untapped_positive_habits", list(habits)),
            ("apps.projects.priority._login_streak", streak),
        ]:
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_sorts_descending_by_score(self):
        today = datetime.date(2026, 4, 16)
        hw_overdue = _make_homework(pk=1, title="Overdue",
                                    due_date=datetime.date(2026, 4, 14))
        chore_weekly = _make_chore(pk=2, title="Clean Room", recurrence="weekly")
        self._patch_all(chores=[chore_weekly], homework=[hw_overdue])
        actions = build_next_actions(_child(), target_date=today, hour=12)
        # Overdue homework (120) > weekly chore Thursday (34)
        self.assertEqual(
            [(a.kind, a.id) for a in actions],
            [("homework", 1), ("chore", 2)],
        )

    def test_tie_break_reward_wins(self):
        today = datetime.date(2026, 4, 16)
        a = _make_chore(pk=1, title="Apple", recurrence="daily")
        b = _make_chore(pk=2, title="Banana", recurrence="daily",
                        reward=Decimal("1.00"))
        self._patch_all(chores=[a, b])
        actions = build_next_actions(_child(), target_date=today, hour=12)
        # Both score 70 → reward wins, so Banana first
        self.assertEqual(actions[0].id, 2)

    def test_trims_to_limit(self):
        today = datetime.date(2026, 4, 16)
        chores = [
            _make_chore(pk=i, title=f"Chore {i}", recurrence="daily")
            for i in range(30)
        ]
        self._patch_all(chores=chores)
        actions = build_next_actions(
            _child(), target_date=today, hour=12, limit=5,
        )
        self.assertEqual(len(actions), 5)
