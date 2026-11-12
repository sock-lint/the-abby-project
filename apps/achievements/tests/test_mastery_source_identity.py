"""Named category badge promises survive registered MCP taxonomy edits."""
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements import criteria
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService, SkillService
from apps.activity.models import ActivityEvent
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryBadgeIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Category badge identity", parents=[{
            "username": "category-badge-parent", "is_staff": True,
        }], children=[{"username": "category-badge-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Life Skills")
        self.other = SkillCategory.objects.create(name="Other practice")
        self.skill = Skill.objects.create(category=self.category, name="Time Management")
        SkillService.award_xp(self.child, self.skill, 100)

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:catalog", "mcp:author", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def badge(self, kind="category_mastery", **values):
        rule = {"category": "Life Skills", **({"min_level": 1} if kind == "category_mastery" else {"count": 1})}
        return Badge.objects.get(pk=self.wire("create_badge", {
            "name": "Synthetic category promise", "description": "An existing category goal",
            "criteria_type": kind, "criteria_value": {**rule, **values},
            "xp_bonus": 0, "award_coins": False,
        })["id"])

    def rename(self, *, retire=False):
        self.wire("update_category", {
            "category_id": self.category.pk, "name": "Everyday practice", "is_retired": retire,
        })

    def grade(self, payload=None):
        client = APIClient()
        client.force_authenticate(self.child)
        payload = payload or {
            "subject": "Math", "assessment": "Synthetic quiz", "grade_format": "percentage",
            "score": "80", "client_entry_id": str(uuid4()),
        }
        response = client.post("/api/chronicle/grades/", payload, format="json")
        self.assertIn(response.status_code, (200, 201), response.data)
        return response.data, payload

    def assert_earned(self, badge):
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def evaluate(self, *, scope="skill_xp"):
        return BadgeService.evaluate_badges(self.child, scopes={scope})

    def retained(self, category, lookup, provenance=None):
        return RPGContentOverride.objects.create(
            family=self.parent.family, model_label="achievements.skillcategory", object_id=category.pk,
            source_lookup=lookup,
            values={"_authoring": provenance or {"version": 1, "source": "mcp"}},
        )

    def completed_project(self, category=None):
        return Project.objects.create(
            title="Synthetic completed project", assigned_to=self.child, created_by=self.parent,
            category=category or self.category, status=Project.Status.COMPLETED,
        )

    def test_mastery_category_rename_still_awards_during_real_grade_capture(self):
        badge = self.badge()
        self.rename()
        saved, _ = self.grade()
        self.assertEqual(saved["reward_receipt"]["xp_awarded"], 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 110)
        self.assert_earned(badge)
        badge.refresh_from_db()
        self.assertEqual(badge.criteria_value, {"category": "Life Skills", "min_level": 1})

    def test_mastery_multiple_renames_and_retirement_preserve_the_original_rule(self):
        badge = self.badge()
        self.rename()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Daily practice", "is_retired": True})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning", "is_retired": True})
        self.assertEqual(self.evaluate(), [badge])
        self.assert_earned(badge)
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=self.category.pk)
        self.assertEqual(source.source_lookup, {"name": "Life Skills"})

    def test_mastery_source_less_canonical_and_unrelated_edits_remain_eligible(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        badge = self.badge()
        self.wire("update_category", {"category_id": self.other.pk, "name": "Unrelated edited practice"})
        self.assertEqual(self.evaluate(), [badge])

    def test_mastery_restored_name_and_retained_match_are_one_identity(self):
        badge = self.badge()
        self.rename()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Life Skills"})
        self.assertEqual(self.evaluate(), [badge])

    def test_mastery_namesake_cannot_replace_or_compete_with_the_retained_category(self):
        self.badge()
        self.rename()
        namesake = SkillCategory.objects.create(name="Life Skills")
        other_skill = Skill.objects.create(category=namesake, name="Namesake skill")
        SkillService.award_xp(self.child, other_skill, 100)
        self.assertEqual(self.evaluate(), [])
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())

    def test_mastery_distinct_retained_categories_are_ambiguous(self):
        self.badge()
        self.rename()
        self.retained(self.other, {"name": "Life Skills"})
        other_skill = Skill.objects.create(category=self.other, name="Other skill")
        SkillService.award_xp(self.child, other_skill, 100)
        self.assertEqual(self.evaluate(), [])

    def test_mastery_retained_provenance_and_complete_lookup_must_be_exact(self):
        badge = self.badge()
        self.rename()
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=self.category.pk)
        for provenance in ({}, {"version": 2, "source": "mcp"}, {"version": 1, "source": "other"},
                           {"version": 1, "source": "mcp", "extra": True}):
            with self.subTest(provenance=provenance):
                source.values = {"_authoring": provenance}
                source.save(update_fields=["values"])
                self.assertFalse(criteria.check(self.child, badge))
        source.values = {"_authoring": {"version": 1, "source": "mcp"}}
        source.source_lookup = {"name": "Life Skills", "extra": True}
        source.save(update_fields=["values", "source_lookup"])
        self.assertFalse(criteria.check(self.child, badge))

    def test_mastery_keeps_exact_case_and_current_membership_and_thresholds(self):
        self.assertFalse(criteria._category_mastery(self.child, {"category": "LIFE SKILLS", "min_level": 1}))
        self.assertFalse(criteria._category_mastery(self.child, {"category": "Life Skills", "min_level": 2}))
        self.rename()
        self.wire("update_skill", {"skill_id": self.skill.pk, "category_id": self.other.pk, "clear_subject": True})
        self.assertFalse(criteria._category_mastery(self.child, {"category": "Life Skills", "min_level": 1}))

    def test_earned_mastery_and_saved_grade_replay_survive_rename_retire_and_restore(self):
        badge = self.badge()
        saved, payload = self.grade()
        self.assert_earned(badge)
        earned_id = UserBadge.objects.get(user=self.child, badge=badge).pk
        before = (SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points,
                  CoinLedger.objects.count(), ActivityEvent.objects.filter(event_type="award.badge").count())
        self.rename(retire=True)
        self.assertEqual(self.grade(payload)[0], saved)
        self.assertEqual(self.evaluate(), [])
        self.wire("update_category", {"category_id": self.category.pk, "name": "Life Skills", "is_retired": False})
        self.assertEqual(self.evaluate(), [])
        self.assertEqual(UserBadge.objects.get(user=self.child, badge=badge).pk, earned_id)
        self.assertEqual((SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points,
                          CoinLedger.objects.count(), ActivityEvent.objects.filter(event_type="award.badge").count()), before)

    def test_named_project_category_rename_keeps_the_completed_project_goal(self):
        self.completed_project()
        badge = self.badge("category_projects")
        self.rename()
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_named_project_category_is_case_insensitive_before_rename(self):
        self.completed_project()
        badge = self.badge("category_projects", category="LIFE SKILLS")
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_named_project_category_retained_name_remains_case_insensitive_after_retirement(self):
        self.completed_project()
        badge = self.badge("category_projects", category="lIfE sKiLlS")
        self.rename(retire=True)
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_named_project_current_and_retained_case_insensitive_collision_fails_closed(self):
        self.completed_project()
        self.badge("category_projects", category="LIFE SKILLS")
        self.rename()
        namesake = SkillCategory.objects.create(name="life skills")
        self.completed_project(namesake)
        self.assertEqual(self.evaluate(scope="project"), [])

    def test_named_project_distinct_retained_case_insensitive_categories_are_ambiguous(self):
        self.completed_project()
        self.completed_project(self.other)
        self.badge("category_projects", category="LIFE SKILLS")
        self.rename()
        self.retained(self.other, {"name": "life skills"})
        self.assertEqual(self.evaluate(scope="project"), [])

    def test_named_project_dangling_or_inexact_sources_do_not_compete_with_canonical_category(self):
        self.completed_project()
        badge = self.badge("category_projects", category="LIFE SKILLS")
        self.retained(self.other, {"name": "Life Skills", "extra": True})
        source = self.retained(self.category, {"name": "life skills"})
        source.object_id += 10000
        source.save(update_fields=["object_id"])
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_named_project_missing_category_does_not_use_an_unrelated_completed_project(self):
        self.completed_project(self.other)
        self.badge("category_projects", category="Missing category")
        self.assertEqual(self.evaluate(scope="project"), [])

    def test_named_project_invalid_retained_metadata_cannot_supply_a_category(self):
        badge = self.badge("category_projects", category="LIFE SKILLS")
        self.completed_project()
        self.rename()
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=self.category.pk)
        for provenance, lookup in (
            ({"version": 2, "source": "mcp"}, {"name": "Life Skills"}),
            ({"version": 1, "source": "other"}, {"name": "Life Skills"}),
            ({"version": 1, "source": "mcp", "extra": True}, {"name": "Life Skills"}),
            ({"version": 1, "source": "mcp"}, {"name": "Life Skills", "extra": True}),
        ):
            with self.subTest(provenance=provenance, lookup=lookup):
                source.values, source.source_lookup = {"_authoring": provenance}, lookup
                source.save(update_fields=["values", "source_lookup"])
                self.assertFalse(criteria.check(self.child, badge))

    def test_named_project_restored_current_and_retained_match_are_one_identity(self):
        self.completed_project()
        badge = self.badge("category_projects", category="LIFE SKILLS")
        self.rename()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Life Skills"})
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_plural_project_goal_keeps_distinct_saved_category_count_after_rename(self):
        self.completed_project()
        self.completed_project(self.other)
        badge = self.badge("category_projects", categories=2, category="Ignored named category")
        self.rename()
        self.assertEqual(self.evaluate(scope="project"), [badge])

    def test_any_project_category_keeps_existing_literal_name_semantics(self):
        self.completed_project()
        self.badge("category_projects", category="any")
        self.rename()
        self.assertEqual(self.evaluate(scope="project"), [])
