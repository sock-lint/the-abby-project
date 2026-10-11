"""Rendered Django responses shared by the React and Unity contract checks.

Keep values deterministic by controlling test inputs, clock and token entropy;
the views, serializers, authentication, pagination and game loop remain real.
"""
import json
import os
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.quests.models import DailyChallenge
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family


FIXTURE_DIR = Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures"
FIXED_NOW = datetime(2026, 10, 10, 19, 0, tzinfo=datetime_timezone.utc)
SYNTHETIC_TOKEN = "0123456789012345678901234567890123456789"


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class SharedApiResponseFixtureTests(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        # Pin wire identities even when the full suite advances PostgreSQL sequences.
        household = make_family(
            "Fixture Family", family_id=1,
            parents=[{
                "id": 6, "username": "fixture-parent", "password": "synthetic-password",
                "display_name": "Fixture Parent",
            }],
            children=[{
                "id": 7, "username": "fixture-child", "password": "synthetic-password",
                "display_name": "Fixture Child", "theme": "hyrule",
            }, {"id": 8, "username": "fixture-sibling"}],
        )
        family, parent = household.family, household.parents[0]
        self.child, sibling = household.children
        outsider = make_family(
            "Other Fixture Family", family_id=2,
            children=[{"id": 99, "username": "fixture-outsider"}],
        ).children[0]
        category = SkillCategory.objects.create(id=1, name="Language Arts")
        self.skill = Skill.objects.create(id=2, name="Reading", category=category)
        self.habit = Habit.objects.create(
            id=9, name='Read {a} book "today"', icon="book", user=self.child,
            created_by=parent, xp_reward=5, max_taps_per_day=1, strength=-2,
        )
        HabitSkillTag.objects.create(id=4, habit=self.habit, skill=self.skill, xp_weight=1)
        # Use the production page size (20), including actual safety flag variants.
        for index in range(2, 22):
            Habit.objects.create(
                id=index + 8, name=f"Ritual {index:02d}", user=self.child,
                created_by=parent,
                habit_type="negative" if index == 2 else "both" if index == 3 else "positive",
                is_active=index != 4,
            )
        # Extra rows must not leak into this child's paginated tap surface.
        for habit_id, owner, pending in ((91, sibling, False), (92, outsider, False), (93, self.child, True)):
            Habit.objects.create(
                id=habit_id, name=f"Hidden ritual {habit_id}", user=owner,
                created_by=parent if owner.family_id == family.id else outsider,
                pending_parent_review=pending,
            )
        self.auth_token = Token.objects.create(user=self.child, key="f" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.auth_token.key}")

    def assert_response_fixture(self, response, name, status=200):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        actual = response.json()
        path = FIXTURE_DIR / name
        if os.environ.get("UPDATE_API_CONTRACT_FIXTURES") == "1":
            self.assertFalse(os.environ.get("CI"), "Fixture regeneration is a local, reviewed operation.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        expected = json.loads(path.read_text(encoding="utf-8"))
        # Python value equality treats True == 1 and 5 == 5.0. Canonical JSON
        # preserves these wire types while ignoring object key order.
        self.assertEqual(
            json.dumps(actual, sort_keys=True, indent=2),
            json.dumps(expected, sort_keys=True, indent=2),
            f"API response drifted from {path.name}; review the contract and regenerate deliberately.",
        )
        return actual

    def test_login_and_verified_identity(self):
        with patch("rest_framework.authtoken.models.Token.generate_key", return_value=SYNTHETIC_TOKEN):
            login = self.client.post("/api/auth/", {
                "action": "login", "username": self.child.username, "password": "synthetic-password",
            }, format="json")
        body = self.assert_response_fixture(login, "auth-login-child.json")
        self.assertEqual(body["token"], Token.objects.get(user=self.child).key)
        self.assertFalse(Token.objects.filter(key=self.auth_token.key).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {body['token']}")
        identity = self.assert_response_fixture(self.client.get("/api/auth/me/"), "auth-me-child.json")
        self.assertEqual({key: value for key, value in body.items() if key != "token"}, identity)

    def test_paginated_habits_preserve_scope_and_safety_fields(self):
        first = self.assert_response_fixture(self.client.get("/api/habits/"), "habits-page-1.json")
        second = self.assert_response_fixture(self.client.get(first["next"]), "habits-page-2.json")
        self.assertEqual(first["count"], 21)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual({row["id"] for row in first["results"] + second["results"]}, set(range(9, 30)))
        self.assertTrue(all(row["user"] == self.child.pk for row in first["results"] + second["results"]))
        self.assertFalse(any(row["pending_parent_review"] for row in first["results"] + second["results"]))

    def test_empty_habits_still_use_pagination_envelope(self):
        Habit.objects.filter(user=self.child, pending_parent_review=False).delete()
        self.assert_response_fixture(self.client.get("/api/habits/"), "habits-empty.json")

    def test_confirmed_positive_tap_and_rejected_duplicate(self):
        DailyChallenge.objects.create(
            id=3, user=self.child, date=FIXED_NOW.date(), challenge_type="habits", target_value=2,
        )
        # Only the random input is fixed; no service/serializer result is mocked.
        with patch("apps.rpg.services.random.random", return_value=1.0):
            response = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        body = self.assert_response_fixture(response, "habit-positive-tap.json")
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 5)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).login_streak, body["game_event"]["streak"]["streak"])
        rejected = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        self.assert_response_fixture(rejected, "habit-positive-tap-limit.json", status=400)
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])

    def test_confirmed_positive_tap_without_optional_game_event(self):
        # A missing optional event does not invalidate the persisted base tap.
        # This scenario alone replaces the game-loop boundary, never the view
        # or HabitService result; the ordinary fixture above runs the real loop.
        with patch("apps.rpg.services.GameLoopService.on_task_completed", return_value=None):
            response = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        body = self.assert_response_fixture(response, "habit-positive-tap-no-event.json")
        self.assertIsNone(body["game_event"])
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 5)
