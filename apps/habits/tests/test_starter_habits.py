"""Starter routines are durable assignments, never a mutation of a read."""
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.habits.models import Habit, HabitLog
from apps.habits.services import HabitService
from config.tests.factories import make_family


class StarterHabitTests(TestCase):
    def setUp(self):
        household = make_family(
            parents=[{"username": "starter-parent"}],
            children=[{"username": "starter-child"}],
        )
        self.parent = household.parents[0]
        self.child = household.children[0]
        self.client = APIClient()

    def install(self, child=None):
        from apps.habits.defaults import ensure_starter_habits

        return ensure_starter_habits(child or self.child, created_by=self.parent)

    def test_new_child_receives_published_twice_daily_teeth_habit(self):
        self.client.force_authenticate(self.parent)
        response = self.client.post("/api/children/", {
            "username": "new-starter-child", "password": "StrongPassword12!",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        habit = Habit.objects.get(user_id=response.data["id"], name="Brush your teeth")
        self.assertEqual(habit.starter_key, "brush_teeth")
        self.assertEqual(habit.icon, "🪥")
        self.assertEqual(habit.habit_type, "positive")
        self.assertEqual(habit.max_taps_per_day, 2)
        self.assertEqual(habit.xp_reward, 5)
        self.assertEqual(habit.created_by, self.parent)
        self.assertTrue(habit.is_active)
        self.assertFalse(habit.pending_parent_review)

    def test_paused_habit_rejects_taps_without_activity_or_rewards(self):
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent,
            name="Brush your teeth", max_taps_per_day=2, is_active=False,
        )
        with patch("apps.achievements.services.AwardService.grant") as award:
            with self.assertRaisesMessage(ValueError, "paused"):
                HabitService.log_tap(self.child, habit, 1)
        habit.refresh_from_db()
        self.assertEqual(habit.strength, 0)
        self.assertFalse(HabitLog.objects.filter(habit=habit).exists())
        award.assert_not_called()

    def test_installation_preserves_renamed_paused_starter_and_logs(self):
        self.install()
        habit = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        HabitLog.objects.create(habit=habit, user=self.child, direction=1)
        Habit.objects.filter(pk=habit.pk).update(
            name="My morning and night routine", xp_reward=12,
            max_taps_per_day=3, strength=7, is_active=False,
        )
        self.install()
        habit.refresh_from_db()
        self.assertEqual(Habit.objects.filter(user=self.child).count(), 1)
        self.assertEqual(habit.name, "My morning and night routine")
        self.assertEqual(habit.xp_reward, 12)
        self.assertEqual(habit.max_taps_per_day, 3)
        self.assertEqual(habit.strength, 7)
        self.assertFalse(habit.is_active)
        self.assertEqual(habit.logs.count(), 1)

    def test_existing_twice_daily_teeth_habit_is_adopted_without_changes(self):
        for name in ("Brush teeth", "BRUSH YOUR TEETH"):
            with self.subTest(name=name):
                habit = Habit.objects.create(
                    user=self.child, created_by=self.parent, name=name,
                    max_taps_per_day=2, xp_reward=11, icon="✨", is_active=False,
                )
                HabitLog.objects.create(habit=habit, user=self.child, direction=1)
                self.install()
                habit.refresh_from_db()
                self.assertEqual(habit.starter_key, "brush_teeth")
                self.assertEqual(habit.name, name)
                self.assertEqual(habit.xp_reward, 11)
                self.assertEqual(habit.icon, "✨")
                self.assertFalse(habit.is_active)
                self.assertEqual(habit.logs.count(), 1)
                self.assertEqual(Habit.objects.filter(user=self.child).count(), 1)
                habit.delete()

    def test_pending_proposal_is_not_published_by_starter_installation(self):
        proposal = Habit.objects.create(
            user=self.child, created_by=self.child, name="Brush teeth",
            max_taps_per_day=2, pending_parent_review=True,
        )
        self.install()
        proposal.refresh_from_db()
        self.assertTrue(proposal.pending_parent_review)
        self.assertIsNone(proposal.starter_key)
        starter = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        self.assertNotEqual(starter.pk, proposal.pk)
        self.assertFalse(starter.pending_parent_review)

    def test_identity_unique_per_child_leaves_custom_habits_unrestricted(self):
        self.install()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Habit.objects.create(
                user=self.child, created_by=self.parent, name="Duplicate",
                starter_key="brush_teeth",
            )
        for _ in range(2):
            Habit.objects.create(user=self.child, created_by=self.parent, name="Custom")
        self.assertEqual(Habit.objects.filter(user=self.child).count(), 3)

    def test_starter_key_is_read_only_in_parent_api(self):
        self.install()
        starter = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        self.client.force_authenticate(self.parent)
        response = self.client.patch(f"/api/habits/{starter.pk}/", {
            "starter_key": "replacement", "name": "Family teeth routine",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        starter.refresh_from_db()
        self.assertEqual(starter.starter_key, "brush_teeth")
        self.assertEqual(starter.name, "Family teeth routine")
        self.assertEqual(self.client.get(f"/api/habits/{starter.pk}/").data["starter_key"], "brush_teeth")

    def test_parent_cannot_reassign_starter_to_sibling(self):
        from apps.accounts.models import User

        self.install()
        starter = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        sibling = User.objects.create_user(
            username="starter-sibling", role="child", family=self.child.family,
        )
        from apps.habits.defaults import ensure_starter_habits
        ensure_starter_habits(sibling, created_by=self.parent)
        self.client.force_authenticate(self.parent)
        response = self.client.patch(f"/api/habits/{starter.pk}/", {
            "user": sibling.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        starter.refresh_from_db()
        self.assertEqual(starter.user_id, self.child.pk)

    def test_reads_do_not_recreate_deleted_starter(self):
        self.install()
        Habit.objects.filter(user=self.child, starter_key="brush_teeth").delete()
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/habits/").status_code, 200)
        self.assertFalse(Habit.objects.filter(user=self.child).exists())

    def test_two_starter_taps_complete_day_and_third_grants_nothing(self):
        self.install()
        habit = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        self.client.force_authenticate(self.child)
        with patch("apps.rpg.services.GameLoopService.on_task_completed", return_value=None) as game:
            for _ in range(2):
                self.assertEqual(self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}).status_code, 200)
            rejected = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1})
        self.assertEqual(rejected.status_code, 400)
        habit.refresh_from_db()
        self.assertEqual(habit.strength, 2)
        self.assertEqual(habit.logs.count(), 2)
        self.assertEqual(game.call_count, 2)

    def test_child_installation_failure_rolls_back_account(self):
        from apps.accounts.models import User

        self.client.force_authenticate(self.parent)
        with patch("apps.habits.defaults.ensure_starter_habits", side_effect=RuntimeError("installer failed")):
            with self.assertRaisesMessage(RuntimeError, "installer failed"):
                self.client.post("/api/children/", {
                    "username": "failed-starter-child", "password": "StrongPassword12!",
                }, format="json")
        self.assertFalse(User.objects.filter(username="failed-starter-child").exists())

    def test_migration_backfills_every_child_without_parent_habits(self):
        other = make_family(
            parents=[{"username": "other-starter-parent"}],
            children=[{"username": "other-starter-child"}, {"username": "other-inactive-child", "is_active": False}],
        )
        migration = import_module("apps.habits.migrations.0007_habit_starter_key")
        editor = SimpleNamespace(connection=connection)
        migration.install_starter_habits(apps, editor)
        migration.install_starter_habits(apps, editor)
        for child in (self.child, *other.children):
            self.assertEqual(Habit.objects.filter(user=child, starter_key="brush_teeth").count(), 1)
        self.assertFalse(Habit.objects.filter(user__role="parent").exists())
        self.assertEqual(Habit.objects.get(user=other.children[0]).created_by, other.parents[0])

    def test_migration_adopts_existing_routine_without_resetting_history(self):
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Brush teeth",
            max_taps_per_day=2, xp_reward=14, strength=9, is_active=False,
        )
        log = HabitLog.objects.create(habit=habit, user=self.child, direction=1)
        migration = import_module("apps.habits.migrations.0007_habit_starter_key")
        migration.install_starter_habits(apps, SimpleNamespace(connection=connection))
        habit.refresh_from_db()
        self.assertEqual(habit.starter_key, "brush_teeth")
        self.assertEqual(habit.name, "Brush teeth")
        self.assertEqual(habit.xp_reward, 14)
        self.assertEqual(habit.strength, 9)
        self.assertFalse(habit.is_active)
        self.assertEqual(list(habit.logs.values_list("pk", flat=True)), [log.pk])
        self.assertEqual(Habit.objects.filter(user=self.child).count(), 1)

    def test_parent_accounts_never_receive_starters(self):
        from apps.habits.defaults import ensure_starter_habits

        self.assertEqual(ensure_starter_habits(self.parent), [])
        self.assertFalse(Habit.objects.filter(user=self.parent).exists())

    def test_starter_does_not_cross_household_read_or_edit_boundaries(self):
        self.install()
        habit = Habit.objects.get(user=self.child, starter_key="brush_teeth")
        other = make_family(
            parents=[{"username": "outside-starter-parent"}],
            children=[{"username": "outside-starter-child"}],
        )
        for user in (other.parents[0], other.children[0]):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(f"/api/habits/{habit.pk}/").status_code, 404)
        self.client.force_authenticate(other.parents[0])
        self.assertEqual(self.client.patch(f"/api/habits/{habit.pk}/", {"is_active": False}).status_code, 404)
