"""Preserve current-name unions and uncategorized category-project awards."""
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.achievements import criteria
from apps.achievements.models import Badge, SkillCategory, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryProjectsCompatibilityTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Category projects compatibility", parents=[{
            "username": "project-category-parent", "is_staff": True,
        }], children=[{"username": "project-category-child"}])
        self.parent, self.child = family.parents[0], family.children[0]

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def category(self, name):
        return SkillCategory.objects.get(pk=self.wire("create_category", {"name": name})["id"])

    def badge(self, value):
        return Badge.objects.get(pk=self.wire("create_badge", {
            "name": "Category project compatibility badge", "description": "Saved category project rule",
            "criteria_type": "category_projects", "criteria_value": value, "award_coins": False,
        })["id"])

    def completed(self, category=None):
        return Project.objects.create(title="Completed compatibility project", assigned_to=self.child,
            created_by=self.parent, category=category, status=Project.Status.COMPLETED)

    def assert_awards_once(self, badge):
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)

    def test_current_case_variant_categories_count_the_union_at_the_saved_threshold(self):
        first = SkillCategory.objects.create(name="Practice")
        second = SkillCategory.objects.create(name="PRACTICE")
        badge = self.badge({"category": "practice", "count": 2})
        self.completed(first)
        self.assertFalse(criteria.check(self.child, badge))
        self.completed(second)
        self.assert_awards_once(badge)

    def test_mcp_created_current_categories_keep_union_despite_own_source_overrides(self):
        first, second = self.category("Practice"), self.category("PRACTICE")
        badge = self.badge({"category": "pRaCtIcE", "count": 2})
        self.completed(first)
        self.completed(second)
        self.assertEqual(RPGContentOverride.objects.filter(model_label="achievements.skillcategory").count(), 2)
        self.assert_awards_once(badge)

    def test_mcp_rename_to_a_current_case_variant_keeps_both_current_categories(self):
        first, second = self.category("Practice"), self.category("Other category")
        self.wire("update_category", {"category_id": second.pk, "name": "PRACTICE"})
        badge = self.badge({"category": "practice", "count": 2})
        self.completed(first)
        self.completed(second)
        self.assert_awards_once(badge)

    def test_case_only_rename_retains_a_current_match_rather_than_competing_alias(self):
        first, second = self.category("Practice"), self.category("PRACTICE")
        self.wire("update_category", {"category_id": first.pk, "name": "pRactice"})
        badge = self.badge({"category": "practice", "count": 2})
        self.completed(first)
        self.completed(second)
        self.assert_awards_once(badge)

    def test_current_union_is_not_limited_to_two_case_variants(self):
        categories = [self.category(name) for name in ("Practice", "PRACTICE", "practice")]
        badge = self.badge({"category": "pRaCtIcE", "count": 3})
        for category in categories:
            self.completed(category)
        self.assert_awards_once(badge)

    def test_omitted_category_counts_only_uncategorized_completed_projects(self):
        category = self.category("Named practice")
        badge = self.badge({"count": 2})
        self.completed()
        self.completed(category)
        self.assertFalse(criteria.check(self.child, badge))
        self.completed()
        self.assert_awards_once(badge)

    def test_default_omitted_category_threshold_remains_three_uncategorized_projects(self):
        badge = self.badge({})
        self.completed()
        self.completed()
        self.assertFalse(criteria.check(self.child, badge))
        self.completed()
        self.assert_awards_once(badge)

    def test_legacy_explicit_null_category_keeps_uncategorized_semantics(self):
        badge = Badge.objects.create(name="Legacy null category", description="Historical criteria",
            criteria_type="category_projects", criteria_value={"category": None, "count": 1}, award_coins=False)
        self.completed()
        self.assert_awards_once(badge)

    def test_plural_categories_keeps_distinct_nonnull_count_and_ignores_named_selector(self):
        first, second = self.category("Practice"), self.category("Other category")
        badge = self.badge({"categories": 2, "category": "An ignored selector", "count": 100})
        self.completed(first)
        self.completed()
        self.assertFalse(criteria.check(self.child, badge))
        self.completed(second)
        self.assert_awards_once(badge)

    def test_renamed_retained_identity_competing_with_current_union_still_fails_closed(self):
        retained = self.category("Practice")
        self.wire("update_category", {"category_id": retained.pk, "name": "Renamed retained practice"})
        # Persisted legacy aliases remain ambiguous even though authenticated
        # writers now prevent creating this retained/current conflict.
        current = [SkillCategory.objects.create(name=name) for name in ("PRACTICE", "practice")]
        badge = self.badge({"category": "pRaCtIcE", "count": 1})
        for category in [retained, *current]:
            self.completed(category)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def test_distinct_renamed_retained_identities_still_fail_closed(self):
        first, second = self.category("Practice"), self.category("PRACTICE")
        # Reconstruct the legacy state without bypassing writer admission in
        # the workflow under test; its original source overrides stay intact.
        SkillCategory.objects.filter(pk=first.pk).update(name="Retained original one")
        SkillCategory.objects.filter(pk=second.pk).update(name="Retained original two")
        badge = self.badge({"category": "practice", "count": 1})
        self.completed(first)
        self.completed(second)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
