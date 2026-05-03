"""Tests for Tier-2.3 habit MCP tools."""
from __future__ import annotations

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    CreateHabitIn,
    DeleteHabitIn,
    GetHabitIn,
    ListHabitsIn,
    LogHabitIn,
    UpdateHabitIn,
)
from apps.mcp_server.tools import habits as hb
from apps.accounts.models import User
from apps.habits.models import Habit, HabitLog


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CreateHabitTests(_Base):
    def test_parent_creates_for_child(self) -> None:
        with override_user(self.parent):
            r = hb.create_habit(CreateHabitIn(
                name="Floss", habit_type="positive",
                user_id=self.child.id,
            ))
        habit = Habit.objects.get(pk=r["id"])
        self.assertEqual(habit.user, self.child)
        self.assertEqual(habit.created_by, self.parent)

    def test_child_creates_for_self(self) -> None:
        with override_user(self.child):
            r = hb.create_habit(CreateHabitIn(name="Stretch"))
        habit = Habit.objects.get(pk=r["id"])
        self.assertEqual(habit.user, self.child)

    def test_child_cannot_create_for_other(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            hb.create_habit(CreateHabitIn(name="X", user_id=other.id))


class UpdateAndDeleteTests(_Base):
    def test_parent_update(self) -> None:
        habit = Habit.objects.create(
            name="h", user=self.child, created_by=self.parent,
        )
        with override_user(self.parent):
            hb.update_habit(UpdateHabitIn(
                habit_id=habit.id, name="new", max_taps_per_day=3,
            ))
        habit.refresh_from_db()
        self.assertEqual(habit.name, "new")
        self.assertEqual(habit.max_taps_per_day, 3)

    def test_child_cannot_update(self) -> None:
        habit = Habit.objects.create(
            name="h", user=self.child, created_by=self.child,
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            hb.update_habit(UpdateHabitIn(habit_id=habit.id, name="x"))

    def test_delete(self) -> None:
        habit = Habit.objects.create(
            name="h", user=self.child, created_by=self.parent,
        )
        with override_user(self.parent):
            r = hb.delete_habit(DeleteHabitIn(habit_id=habit.id))
        self.assertTrue(r["deleted"])


class LogHabitTests(_Base):
    def test_child_logs_own_habit(self) -> None:
        habit = Habit.objects.create(
            name="Exercise", user=self.child, created_by=self.child,
            habit_type="positive",
        )
        with override_user(self.child):
            r = hb.log_habit(LogHabitIn(habit_id=habit.id, amount=1))
        self.assertEqual(
            HabitLog.objects.filter(habit=habit).count(), 1,
        )
        # Positive tap fires the game loop
        self.assertIsNotNone(r.get("game_event"))

    def test_cannot_log_others_habit(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        habit = Habit.objects.create(
            name="h", user=other, created_by=other,
        )
        # Audit C8: cross-user lookup now returns NotFound (no existence
        # leak between siblings).
        with override_user(self.child), self.assertRaises(MCPNotFoundError):
            hb.log_habit(LogHabitIn(habit_id=habit.id))

    def test_negative_tap_on_positive_habit_rejected(self) -> None:
        habit = Habit.objects.create(
            name="h", user=self.child, created_by=self.child,
            habit_type="positive",
        )
        with override_user(self.child), self.assertRaises(MCPValidationError):
            hb.log_habit(LogHabitIn(habit_id=habit.id, amount=-1))

    def test_log_rejected_over_daily_cap(self) -> None:
        habit = Habit.objects.create(
            name="Brush teeth", user=self.child, created_by=self.child,
            habit_type="positive", max_taps_per_day=2,
        )
        with override_user(self.child):
            hb.log_habit(LogHabitIn(habit_id=habit.id, amount=1))
            hb.log_habit(LogHabitIn(habit_id=habit.id, amount=1))
            with self.assertRaises(MCPValidationError):
                hb.log_habit(LogHabitIn(habit_id=habit.id, amount=1))


class ListAndGetTests(_Base):
    def test_child_sees_only_own(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        Habit.objects.create(
            name="mine", user=self.child, created_by=self.child,
        )
        Habit.objects.create(
            name="theirs", user=other, created_by=other,
        )
        with override_user(self.child):
            r = hb.list_habits(ListHabitsIn())
        names = [h["name"] for h in r["habits"]]
        self.assertEqual(names, ["mine"])

    def test_get_own_habit(self) -> None:
        habit = Habit.objects.create(
            name="h", user=self.child, created_by=self.child,
        )
        with override_user(self.child):
            r = hb.get_habit(GetHabitIn(habit_id=habit.id))
        self.assertEqual(r["id"], habit.id)

    def test_get_others_habit_denied(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        habit = Habit.objects.create(
            name="h", user=other, created_by=other,
        )
        # Audit C8: same doctrine — cross-user lookups return NotFound.
        with override_user(self.child), self.assertRaises(MCPNotFoundError):
            hb.get_habit(GetHabitIn(habit_id=habit.id))
