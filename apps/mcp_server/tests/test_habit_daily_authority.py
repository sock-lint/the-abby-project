"""Habit and legacy daily tools retain current household authority over SDK calls."""
from contextlib import contextmanager
from unittest.mock import patch
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.mcp_server.auth import _resolve_access
from apps.mcp_server.context import get_current_user, override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import daily_challenges, habits
from apps.quests.models import DailyChallenge
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family, make_oauth_token


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   MCP_RESOURCE_URL="http://synthetic.invalid/mcp")
class HabitDailyAuthorityTests(TestCase):
    def setUp(self):
        home = make_family("Habit authority household", parents=[{"username": "habit-authority-parent", "is_staff": True}],
                           children=[{"username": "habit-authority-child"}])
        self.parent, self.child = home.parents[0], home.children[0]
        other = make_family("Foreign habit authority household", children=[{"username": "habit-authority-foreign"}])
        self.other, self.foreign = other.family, other.children[0]
        token, _ = make_oauth_token(self.parent, scope="mcp:read mcp:write")
        self.actor, self.scopes = _resolve_access(token.token)
        self.habit = self.make_habit(self.child)
        category = SkillCategory.objects.create(name="Habit authority skills")
        self.skill = Skill.objects.create(name="Habit authority practice", category=category)

    def make_habit(self, user):
        return Habit.objects.create(name="Saved private routine", user=user, created_by=self.parent, xp_reward=0)

    def daily(self, user=None):
        user = user or self.child
        return DailyChallenge.objects.create(
            user=user, date=timezone.localdate(timezone=ZoneInfo(user.family.timezone)),
            challenge_type="chore", target_value=1, current_progress=1,
            completed_at=timezone.now(), coin_reward=11, xp_reward=0,
        )

    def wire(self, name, params=None, *, actor=None, scopes=None, confirmation=True):
        with override_user(actor or self.actor, scopes=self.scopes if scopes is None else scopes):
            result = async_to_sync(mcp.call_tool)(name, {"params": params or {}, "confirmation": confirmation})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def assert_error(self, payload, code):
        self.assertIn("error", payload, payload)
        self.assertEqual(payload["error"]["code"], code, payload)

    def test_all_habit_tools_recheck_cached_actor_authority(self):
        for changes in ({"is_active": False}, {"is_staff": False}, {"role": "child"}, {"family": self.other}):
            for name in ("list_habits", "get_habit", "create_habit", "update_habit", "delete_habit",
                         "set_habit_skill_tags", "log_habit"):
                # Each call has its own subject so an unguarded deletion cannot
                # make a later positive reproduction pass accidentally.
                habit = self.make_habit(self.parent if name == "log_habit" else self.child)
                params = {
                    "list_habits": {}, "get_habit": {"habit_id": habit.pk},
                    "create_habit": {"name": "Unauthorized new routine", "user_id": self.child.pk},
                    "update_habit": {"habit_id": habit.pk, "name": "Unauthorized change"},
                    "delete_habit": {"habit_id": habit.pk},
                    "set_habit_skill_tags": {"habit_id": habit.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]},
                    "log_habit": {"habit_id": habit.pk},
                }[name]
                get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
                try:
                    with self.subTest(tool=name, changes=changes):
                        self.assert_error(self.wire(name, params), "permission_denied")
                finally:
                    get_user_model().objects.filter(pk=self.parent.pk).update(
                        family_id=self.parent.family_id, role="parent", is_staff=True, is_active=True,
                    )

    def test_daily_read_and_claim_recheck_cached_actor_authority(self):
        self.daily()
        for changes in ({"is_active": False}, {"is_staff": False}, {"role": "child"}, {"family": self.other}):
            get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
            try:
                for name in ("get_daily_challenge", "claim_daily_challenge"):
                    with self.subTest(tool=name, changes=changes):
                        self.assert_error(self.wire(name, {"user_id": self.child.pk}), "permission_denied")
            finally:
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    family_id=self.parent.family_id, role="parent", is_staff=True, is_active=True,
                )
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").exists())
        self.assertEqual(DailyChallenge.objects.get(user=self.child).coin_reward, 11)

    def test_habit_creation_rechecks_target_after_scalar_resolution(self):
        original = habits.resolve_child_in_family

        def depart(actor, requested):
            target = original(actor, requested)
            get_user_model().objects.filter(pk=target.pk).update(family=self.other)
            return target

        with patch.object(habits, "resolve_child_in_family", side_effect=depart):
            self.assert_error(self.wire("create_habit", {"name": "Departed routine", "user_id": self.child.pk}), "not_found")
        self.assertFalse(Habit.objects.filter(name="Departed routine").exists())

    def test_daily_target_departure_cannot_materialize_or_claim_in_new_household(self):
        original = daily_challenges.resolve_target_user

        def depart(actor, requested):
            target = original(actor, requested)
            get_user_model().objects.filter(pk=target.pk).update(family=self.other)
            return target

        for name in ("get_daily_challenge", "claim_daily_challenge"):
            if name == "claim_daily_challenge":
                self.daily()
            with self.subTest(tool=name), patch.object(daily_challenges, "resolve_target_user", side_effect=depart):
                self.assert_error(self.wire(name, {"user_id": self.child.pk}), "not_found")
            if name == "get_daily_challenge":
                self.assertFalse(DailyChallenge.objects.filter(user=self.child).exists())
            self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").exists())
            get_user_model().objects.filter(pk=self.child.pk).update(family_id=self.parent.family_id)

    def test_serialization_uses_fresh_current_actor(self):
        original = habits._habit_to_dict
        visited = []

        def serialize(habit):
            visited.append((habit.pk, get_current_user()))
            return original(habit)

        with patch.object(habits, "_habit_to_dict", side_effect=serialize):
            self.assertEqual(self.wire("get_habit", {"habit_id": self.habit.pk})["id"], self.habit.pk)
        self.assertEqual([pk for pk, _ in visited], [self.habit.pk])
        self.assertIsNot(visited[0][1], self.actor)
        self.assertEqual(visited[0][1].family_id, self.parent.family_id)

    def test_family_list_does_not_adopt_unlocked_late_join(self):
        # A member joining after the ordered batch was selected has not been
        # locked and must wait for a later request to expose household content.
        outsider = self.make_habit(self.foreign)
        from apps.mcp_server import legacy_household
        original_context = legacy_household.household_context

        @contextmanager
        def join_after_lock(*args, **kwargs):
            with original_context(*args, **kwargs) as members:
                get_user_model().objects.filter(pk=self.foreign.pk).update(family=self.parent.family)
                yield members

        with patch.object(legacy_household, "household_context", side_effect=join_after_lock):
            rows = self.wire("list_habits")["habits"]
        self.assertNotIn(outsider.pk, {row["id"] for row in rows})
        self.assertIn(outsider.pk, {row["id"] for row in self.wire("list_habits")["habits"]})

    def test_parent_child_self_scope_confirmation_and_foreign_controls(self):
        own = self.wire("create_habit", {"name": "Parent self routine"})
        self.assertEqual(Habit.objects.get(pk=own["id"]).user_id, self.parent.pk)
        child_own = self.wire("create_habit", {"name": "Child self routine"}, actor=self.child)
        self.assertEqual(Habit.objects.get(pk=child_own["id"]).user_id, self.child.pk)
        self.assert_error(self.wire("create_habit", {"name": "Sibling routine", "user_id": self.foreign.pk}, actor=self.child),
                          "permission_denied")
        foreign_habit = self.make_habit(self.foreign)
        for name in ("get_habit", "update_habit", "delete_habit", "set_habit_skill_tags"):
            with self.subTest(tool=name):
                params = {"habit_id": foreign_habit.pk}
                if name == "set_habit_skill_tags":
                    params["skill_tags"] = []
                self.assert_error(self.wire(name, params), "not_found")
        self.assert_error(self.wire("create_habit", {"name": "Foreign routine", "user_id": self.foreign.pk}), "not_found")
        self.assert_error(self.wire("get_daily_challenge", {"user_id": self.foreign.pk}), "not_found")
        self.assert_error(self.wire("update_habit", {"habit_id": self.habit.pk}, actor=self.child), "permission_denied")
        self.assert_error(self.wire("update_habit", {"habit_id": self.habit.pk}, scopes=frozenset({"mcp:read"})),
                          "permission_denied")
        self.assert_error(self.wire("update_habit", {"habit_id": self.habit.pk}, confirmation=False), "confirmation_required")
        self.assertEqual(self.wire("get_habit", {"habit_id": self.habit.pk})["name"], "Saved private routine")
        tags = {"habit_id": self.habit.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 2}]}
        self.assertEqual(self.wire("set_habit_skill_tags", tags, actor=self.child)["id"], self.habit.pk)
        self.assertEqual(HabitSkillTag.objects.get(habit=self.habit).xp_weight, 2)
        self.assertEqual(self.wire("log_habit", {"habit_id": child_own["id"]}, actor=self.child)["new_strength"], 1)
        self.assertEqual(HabitLog.objects.filter(user=self.child).count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="habit").exists())

    def test_daily_native_receipt_replay_and_child_self_remain_once_only(self):
        daily = self.daily()
        self.assertEqual(self.wire("get_daily_challenge", {"user_id": self.child.pk})["id"], daily.pk)
        first = self.wire("claim_daily_challenge", actor=self.child)
        self.assertEqual((first["coins"], first["already_claimed"]), (11, False))
        second = self.wire("claim_daily_challenge", {"user_id": self.child.pk})
        self.assertTrue(second["already_claimed"])
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
        self.assert_error(self.wire("claim_daily_challenge", {"user_id": self.foreign.pk}, actor=self.child), "permission_denied")
        daily.refresh_from_db()
        self.assertEqual(daily.coin_reward, 0)

    def test_daily_read_and_claim_require_write_scope_before_side_effects(self):
        daily = self.daily()
        params = {"user_id": self.child.pk}
        self.assert_error(self.wire("claim_daily_challenge", params, scopes=frozenset({"mcp:read"})),
                          "permission_denied")
        self.assert_error(self.wire("get_daily_challenge", params, scopes=frozenset({"mcp:read"})),
                          "permission_denied")
        daily.refresh_from_db()
        self.assertEqual(daily.coin_reward, 11)
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").exists())
        self.assertEqual(self.wire("get_daily_challenge", params)["id"], daily.pk)

    def test_cached_deactivated_child_cannot_read_tap_or_claim(self):
        self.daily()
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        for name, params in (("get_habit", {"habit_id": self.habit.pk}),
                             ("log_habit", {"habit_id": self.habit.pk}),
                             ("get_daily_challenge", {}), ("claim_daily_challenge", {})):
            with self.subTest(tool=name):
                self.assert_error(self.wire(name, params, actor=self.child), "permission_denied")
        self.assertFalse(HabitLog.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").exists())

    def test_inactive_subject_saved_habits_stay_readable_without_daily_creation(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        self.assertEqual(self.wire("get_habit", {"habit_id": self.habit.pk})["id"], self.habit.pk)
        self.assertIn(self.habit.pk, {row["id"] for row in self.wire("list_habits")["habits"]})
        self.assert_error(self.wire("get_daily_challenge", {"user_id": self.child.pk}), "not_found")
        self.assert_error(self.wire("claim_daily_challenge", {"user_id": self.child.pk}), "not_found")
        self.assertFalse(DailyChallenge.objects.filter(user=self.child).exists())
