"""Anonymous Reading forecasts share the installed native XP destination."""
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.families.models import Family
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.reading.models import ReadingBook, ReadingDailyReward, ReadingRewardCredit, ReadingSession
from apps.rewards.models import CoinLedger
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingForecastIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Reading forecast identity", parents=[{
            "username": "forecast-identity-parent", "is_staff": True,
        }], children=[{"username": "forecast-identity-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.other = SkillCategory.objects.create(name="Other practice")
        self.skill = Skill.objects.create(category=self.category, name="Reading Comprehension")
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def forecast(self):
        household_models = (User, Family, ReadingBook, ReadingSession, ReadingRewardCredit,
                            ReadingDailyReward, CoinLedger, SkillProgress)
        before = [model.objects.count() for model in household_models]
        with CaptureQueriesContext(connection) as queries, patch(
            "apps.achievements.services.AwardService.grant", side_effect=AssertionError("No forecast grants"),
        ), patch("apps.rpg.services.random.random", side_effect=AssertionError("No forecast randomness")):
            result = self.wire("preview_economy_scenario", {
                "scenarios": [{"days": 1, "reading_minutes_per_day": 10}],
            })["scenarios"][0]
        self.assertEqual([model.objects.count() for model in household_models], before)
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"), query["sql"])
            for model in household_models:
                self.assertNotIn(connection.ops.quote_name(model._meta.db_table), query["sql"])
        return result

    def save_reading(self, *, payload=None):
        if payload is None:
            book = ReadingBook.objects.create(user=self.child, title="Synthetic forecast book",
                                              client_request_id=uuid4(), create_payload={})
            payload = {"book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4())}
        response = self.client.post("/api/reading-sessions/", payload, format="json")
        self.assertIn(response.status_code, (200, 201), response.data)
        return response.data, payload

    def assert_native_parity(self, *, xp=15):
        forecast = self.forecast()
        saved, _ = self.save_reading()
        self.assertEqual(forecast["reading_skill_available"], bool(xp))
        self.assertEqual(forecast["total_distributed_xp"], xp)
        self.assertEqual(saved["reading_reward"]["xp_awarded"], xp)
        self.assertEqual(forecast["source_rewards_per_day"][0]["coins"], saved["reading_reward"]["coins_awarded"])
        progress = SkillProgress.objects.filter(user=self.child, skill_id=self.skill.pk).first()
        self.assertEqual(progress.xp_points if progress else 0, xp)
        return forecast

    def test_source_less_canonical_destination_and_unrelated_rename_remain_supported(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        self.wire("update_category", {"category_id": self.other.pk, "name": "Unrelated changed practice"})
        self.assert_native_parity()

    def test_registered_skill_rename_keeps_forecast_and_native_reading_xp(self):
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading practice"})
        self.assert_native_parity()

    def test_category_rename_and_reparented_retired_skill_keep_installed_destination(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Language practice", "is_retired": True})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading practice",
                                   "category_id": self.other.pk, "clear_subject": True, "is_retired": True})
        self.assert_native_parity()

    def test_missing_source_never_uses_same_skill_name_in_another_category(self):
        self.skill.delete()
        Skill.objects.create(category=self.other, name="Reading Comprehension")
        self.assert_native_parity(xp=0)

    def test_distinct_current_and_retained_categories_fail_closed(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Language practice"})
        namesake = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(category=namesake, name="Reading Comprehension")
        self.assert_native_parity(xp=0)
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

    def test_distinct_current_and_retained_skills_fail_closed(self):
        namesake = Skill.objects.create(category=self.other, name="Another reading skill")
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill",
            object_id=namesake.pk, source_lookup={"name": "Reading Comprehension", "category_id": self.category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        self.assert_native_parity(xp=0)
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

    def test_inexact_retained_provenance_cannot_supply_a_forecast_destination(self):
        self.skill.name = "Reading practice"
        self.skill.save(update_fields=["name"])
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill",
            object_id=self.skill.pk, source_lookup={"name": "Reading Comprehension", "category_id": self.category.pk},
            values={"_authoring": {"version": 2, "source": "mcp"}})
        self.assert_native_parity(xp=0)

    def test_rename_restore_and_forecasts_do_not_rewrite_or_replay_saved_receipts(self):
        saved, payload = self.save_reading()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Language practice"})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading practice"})
        # An anonymous fresh-day assumption stays separate from this child's saved day.
        self.assertEqual(self.forecast()["total_distributed_xp"], 15)
        self.assertEqual(self.save_reading(payload=payload)[0], saved)
        self.wire("update_category", {"category_id": self.category.pk, "name": "Language Arts"})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading Comprehension"})
        self.assertEqual(self.forecast()["total_distributed_xp"], 15)
        self.assertEqual(self.save_reading(payload=payload)[0], saved)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        self.assertEqual(ReadingDailyReward.objects.count(), 1)
        self.assertEqual(ReadingRewardCredit.objects.count(), 1)
