"""Saved category-project selectors retain native current-name coercion."""
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements import criteria
from apps.achievements.availability import badge_goal_is_available, visible_badges
from apps.achievements.models import Badge, SkillCategory, UserBadge
from apps.achievements.services import BadgeService
from apps.projects.models import Project
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryProjectLegacySelectorTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Legacy category selector", parents=[{"username": "legacy-category-parent"}],
                             children=[{"username": "legacy-category-child"}])
        self.parent, self.child = family.parents[0], family.children[0]

    def completed(self, category):
        return Project.objects.create(title="Completed legacy selector project", created_by=self.parent,
                                      assigned_to=self.child, category=category, status="completed")

    def badge(self, selector, count=1):
        return Badge.objects.create(name="Legacy selector badge", description="Saved native selector",
            criteria_type="category_projects", criteria_value={"category": selector, "count": count}, award_coins=False)

    def assert_awards_once(self, badge):
        self.assertTrue(badge_goal_is_available(badge, self.child))
        self.assertTrue(visible_badges(Badge.objects.filter(pk=badge.pk), self.child).exists())
        self.assertTrue(criteria.check(self.child, badge))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)

    def assert_current_selector(self, selector):
        with transaction.atomic():
            try:
                category = SkillCategory.objects.create(name=str(selector))
                self.completed(category)
                self.completed(category)
                self.completed(None)
                badge = self.badge(selector, count=2)
                self.assert_awards_once(badge)
                badge.criteria_value["count"] = 3
                self.assertFalse(criteria.check(self.child, badge))
            finally:
                transaction.set_rollback(True)

    def test_saved_numeric_and_boolean_selectors_keep_current_name_awards(self):
        for selector in (5, 2.5, True, 0, False):
            with self.subTest(selector=selector):
                self.assert_current_selector(selector)

    def test_saved_container_selectors_keep_native_current_name_lookup(self):
        for selector in (["5"], {"x": 1}, [], {}):
            with self.subTest(selector=selector):
                self.assert_current_selector(selector)

    def test_numeric_selector_is_not_reinterpreted_as_a_retained_source_alias(self):
        for alias in (5, "5"):
            for current in (False, True):
                with self.subTest(alias=alias, current=current), transaction.atomic():
                    try:
                        retained = SkillCategory.objects.create(name="Renamed retained category")
                        RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=retained.pk,
                            family=self.parent.family, source_lookup={"name": alias},
                            values={"_authoring": {"version": 1, "source": "mcp"}})
                        self.completed(retained)
                        if current:
                            self.completed(SkillCategory.objects.create(name="5"))
                        badge = self.badge(5)
                        if current:
                            self.assert_awards_once(badge)
                        else:
                            self.assertTrue(badge_goal_is_available(badge, self.child))
                            self.assertFalse(criteria.check(self.child, badge))
                            self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
                            self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
                    finally:
                        transaction.set_rollback(True)
