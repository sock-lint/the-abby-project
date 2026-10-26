"""Anonymous Lab projections retain the installed Reading/mastery identities."""
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService, SkillService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.models import QuestDefinition, QuestSkillTag
from apps.reading.models import ReadingBook
from apps.rpg.models import RPGContentOverride
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial
from config.tests.factories import make_family


READING_CONFIG = {
    "horizon_days": 30, "trials": 1, "active_days_per_week": 7,
    "reading_minutes": 10, "project_minutes": 0, "chores_per_day": 0,
    "habits_per_day": 0, "movement_sessions_per_day": 0, "creations_per_day": 0,
    "journal_per_day": False, "expeditions_per_day": 0,
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LabSourceIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Lab source identities", parents=[{
            "username": "lab-source-parent", "is_staff": True,
        }], children=[{"username": "lab-source-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.language = SkillCategory.objects.create(name="Language Arts")
        self.reading = Skill.objects.create(category=self.language, name="Reading Comprehension")
        self.other = SkillCategory.objects.create(name="Other practice")

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        data = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", data, data)
        return data

    def report(self):
        # Catalog tools must not inspect private records, draw from the process
        # RNG or invoke a native writer, even when retained metadata is needed.
        private_tables = (
            "projects_user", "families_family", "achievements_skillprogress", "achievements_userbadge",
            "rewards_coinledger", "reading_readingbook", "reading_readingsession", "reading_readingdailyreward",
            "rpg_characterprofile", "rpg_userinventory",
        )
        with CaptureQueriesContext(connection) as queries, patch(
            "apps.achievements.services.AwardService.grant", side_effect=AssertionError("Native award in forecast"),
        ), patch("random.random", side_effect=AssertionError("Global RNG in forecast")):
            report = self.wire("simulate_progression_scenario", {"config": READING_CONFIG})
        for row in queries:
            self.assertTrue(row["sql"].lstrip().upper().startswith("SELECT"), row["sql"])
            for table in private_tables:
                self.assertNotIn(connection.ops.quote_name(table), row["sql"])
        return report

    def actual_reading(self):
        book = ReadingBook.objects.create(user=self.child, title="Synthetic Reading book",
            client_request_id=uuid4(), create_payload={})
        client = APIClient()
        client.force_authenticate(self.child)
        response = client.post("/api/reading-sessions/", {
            "book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["reading_reward"]["xp_awarded"]

    def assert_reading_matches_native(self, xp=15):
        report = self.report()
        projected = next(row["xp"] for row in report["flows"]["sources"] if row["source"] == "reading")
        self.assertEqual(projected, xp * 30)
        trial = Trial(READING_CONFIG, load_catalog(), 3)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertEqual(dict(trial.xp), {self.reading.pk: xp} if xp else {})
        self.assertEqual(self.actual_reading(), xp)
        rows = list(SkillProgress.objects.filter(user=self.child, xp_points__gt=0).values_list("skill_id", "xp_points"))
        self.assertEqual(rows, [(self.reading.pk, xp)] if xp else [])

    def test_source_less_canonical_reading_matches_native(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        self.assert_reading_matches_native()

    def test_registered_skill_rename_retains_original_reading_xp(self):
        self.wire("update_skill", {"skill_id": self.reading.pk, "name": "Reading practice"})
        self.assert_reading_matches_native()

    def test_renamed_retired_reparented_reading_keeps_original_destination(self):
        self.wire("update_category", {"category_id": self.language.pk,
            "name": "Language practice", "is_retired": True})
        self.wire("update_skill", {"skill_id": self.reading.pk, "name": "Reading practice",
            "category_id": self.other.pk, "clear_subject": True, "is_retired": True})
        self.assert_reading_matches_native()

    def test_distinct_current_and_retained_category_cannot_redirect_reading(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Language practice"})
        namesake = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(category=namesake, name="Reading Comprehension")
        self.assert_reading_matches_native(0)

    def test_empty_current_category_also_makes_retained_reading_ambiguous(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Language practice"})
        SkillCategory.objects.create(name="Language Arts")
        self.assert_reading_matches_native(0)

    def test_distinct_retained_skill_cannot_redirect_reading(self):
        rogue = Skill.objects.create(category=self.other, name="Unrelated Reading")
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill",
            object_id=rogue.pk, source_lookup={"name": "Reading Comprehension", "category_id": self.language.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        self.assert_reading_matches_native(0)

    def test_missing_reading_never_uses_matching_name_in_another_category(self):
        self.reading.delete()
        Skill.objects.create(category=self.other, name="Reading Comprehension")
        self.assert_reading_matches_native(0)

    def test_renamed_locked_reading_keeps_unlock_eligibility(self):
        self.wire("update_skill", {"skill_id": self.reading.pk, "name": "Reading practice",
            "is_locked_by_default": True})
        self.assert_reading_matches_native(0)

    def test_inexact_retained_metadata_cannot_create_reading_route(self):
        self.reading.name = "Reading practice"
        self.reading.save(update_fields=["name"])
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill",
            object_id=self.reading.pk,
            source_lookup={"name": "Reading Comprehension", "category_id": self.language.pk},
            values={"_authoring": {"version": 2, "source": "mcp"}})
        self.assert_reading_matches_native(0)

    def test_category_qualified_reading_ignores_other_category_namesake(self):
        Skill.objects.create(category=self.other, name="Reading Comprehension")
        self.assert_reading_matches_native()

    def prepare_mastery(self, *, min_level=1):
        self.category = SkillCategory.objects.create(name="Life Skills")
        self.skill = Skill.objects.create(category=self.category, name="Time Management")
        self.badge = Badge.objects.create(name="Synthetic category mastery", criteria_type="category_mastery",
            criteria_value={"category": "Life Skills", "min_level": min_level}, xp_bonus=0, award_coins=False)
        goal = QuestDefinition.objects.create(name="Synthetic tagged mastery award", quest_type="collection",
            target_value=1, duration_days=None, is_repeatable=False, is_system=True, xp_reward=100,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        QuestSkillTag.objects.create(quest_definition=goal, skill=self.skill, xp_weight=1)

    def assert_mastery_matches_native(self, earned=True):
        report = self.report()
        self.assertEqual(report["trace"][-1]["badges_p50"], int(earned))
        # A renamed category cannot suppress the independently tagged award.
        projected_xp = next(row["xp"] for row in report["flows"]["sources"] if row["source"] == "challenges")
        self.assertEqual(projected_xp, 100)
        SkillService.award_xp(self.child, self.skill, 100)
        BadgeService.evaluate_badges(self.child, scopes={"skill_xp", "badges"})
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=self.badge).exists(), earned)

    def test_source_less_canonical_mastery_matches_native(self):
        self.prepare_mastery()
        self.assert_mastery_matches_native()

    def test_registered_category_rename_retains_mastery_projection(self):
        self.prepare_mastery()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.assert_mastery_matches_native()

    def test_retired_renamed_category_retains_mastery_projection(self):
        # Reading keeps an installed route into a retired category. A new
        # tagged challenge correctly cannot offer retired choices, so it is
        # not a suitable source for this retained-award eligibility control.
        badge = Badge.objects.create(name="Retained Reading mastery", criteria_type="category_mastery",
            criteria_value={"category": "Language Arts", "min_level": 1}, xp_bonus=0, award_coins=False)
        self.wire("update_category", {"category_id": self.language.pk,
            "name": "Language practice", "is_retired": True})
        self.assertEqual(self.report()["trace"][-1]["badges_p50"], 1)
        SkillService.award_xp(self.child, self.reading, 100)
        BadgeService.evaluate_badges(self.child, scopes={"skill_xp", "badges"})
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def test_mastery_current_namesake_and_retained_source_fail_closed(self):
        self.prepare_mastery()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        namesake = SkillCategory.objects.create(name="Life Skills")
        # A populated namesake at the right level must never earn the original
        # category's mastery. Both native and model must reject the ambiguity.
        Skill.objects.filter(pk=self.skill.pk).update(category=namesake)
        self.assert_mastery_matches_native(False)

    def test_mastery_uses_current_category_membership(self):
        self.prepare_mastery()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.wire("update_skill", {"skill_id": self.skill.pk,
            "category_id": self.other.pk, "clear_subject": True})
        Skill.objects.create(category=self.category, name="New current requirement")
        self.assert_mastery_matches_native(False)

    def test_mastery_excludes_locked_by_default_skills(self):
        self.prepare_mastery()
        Skill.objects.create(category=self.category, name="Locked practice", is_locked_by_default=True)
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.assert_mastery_matches_native()

    def test_mastery_preserves_required_threshold(self):
        self.prepare_mastery(min_level=3)
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.assert_mastery_matches_native(False)

    def test_mastery_retains_exact_category_case(self):
        self.prepare_mastery()
        self.badge.criteria_value = {"category": "life skills", "min_level": 1}
        self.badge.save(update_fields=["criteria_value"])
        self.assert_mastery_matches_native(False)

    def test_mastery_with_no_current_required_skills_is_unavailable(self):
        self.prepare_mastery()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.wire("update_skill", {"skill_id": self.skill.pk,
            "category_id": self.other.pk, "clear_subject": True})
        self.assert_mastery_matches_native(False)

    def test_detached_trial_retains_identity_without_queries_or_native_awards(self):
        self.prepare_mastery()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.wire("update_skill", {"skill_id": self.reading.pk, "name": "Reading practice"})
        catalog = load_catalog()
        def no_query(*args, **kwargs):
            raise AssertionError("Detached Trial queried the database")
        with connection.execute_wrapper(no_query), patch(
            "apps.achievements.services.AwardService.grant", side_effect=AssertionError("Native writer"),
        ):
            trial = Trial(READING_CONFIG, catalog, 3)
            self.assertEqual([tag.skill.pk for tag in trial.tags["reading"]], [self.reading.pk])
            for day in range(1, 31):
                trial.daily(day)
            self.assertEqual(trial.source_totals["reading"]["xp"], 450)
            self.assertEqual(trial.badges, {self.badge.pk})
            self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)
            trial.evaluate_badges(scopes={"skill_xp", "badges"})
            self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)
