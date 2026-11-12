"""Named goal reads batch distinct selectors without changing native identity rules."""

from copy import deepcopy

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.availability import BadgeGoalAvailability, badge_goal_is_available, visible_badges
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.achievements.source_identity import project_category_resolution, source_identity_matches
from apps.projects.models import Project
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NamedGoalAvailabilityQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        home = make_family("Batched named goals", parents=[{"username": "batch-parent", "is_staff": True}],
            children=[{"username": "batch-child"}])
        cls.parent, cls.child = home.parents[0], home.children[0]

    def badge(self, kind, name):
        return Badge.objects.create(name=f"{kind}-{Badge.objects.count()}", criteria_type=kind,
            criteria_value={"category": name, **({"count": 1} if kind == "category_projects" else {"min_level": 1})},
            xp_bonus=0, award_coins=False)

    def add_goals(self, kind, start, stop, earned=False):
        for index in range(start, stop):
            name = f"Distinct {index}"
            SkillCategory.objects.get_or_create(name=name)
            badge = self.badge(kind, name)
            if earned:
                UserBadge.objects.create(user=self.child, badge=badge)

    def measured(self, read):
        with CaptureQueriesContext(connection) as queries:
            result = read()
        self.assertFalse([q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))])
        return result, len(queries)

    def assert_growth(self, url=None, *, earned=False, staff=False):
        for kind in ("category_projects", "category_mastery"):
            with self.subTest(kind=kind):
                Badge.objects.all().delete()
                self.add_goals(kind, 0, 10, earned)
                client = APIClient()
                client.force_authenticate(self.parent if staff else self.child)
                def read():
                    if url is None:
                        return visible_badges(Badge.objects.all(), self.child).count()
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200)
                    return response.json()
                read()
                small, small_count = self.measured(read)
                self.add_goals(kind, 10, 40, earned)
                large, large_count = self.measured(read)
                if url is None:
                    self.assertEqual((small, large), (10, 40))
                elif url.endswith("summary/"):
                    self.assertEqual((small["total_badges"], large["total_badges"]), (10, 40))
                    self.assertEqual(len(large["badges_earned"]), 40 if earned else 0)
                else:
                    self.assertEqual((small["count"], large["count"]), (10, 40))
                    rows = large["results"]
                    self.assertTrue(all(row.get("badge", row)["catalog_available"] for row in rows))
                self.assertLessEqual(large_count, small_count + 1,
                    f"{kind} distinct selector growth10→40: {small_count}→{large_count}")

    def test_visible_catalog_distinct_selector_query_budget(self):
        self.assert_growth()

    def test_child_catalog_distinct_selector_query_budget(self):
        self.assert_growth("/api/badges/")

    def test_staff_catalog_distinct_selector_query_budget(self):
        self.assert_growth("/api/badges/", staff=True)

    def test_unearned_summary_distinct_selector_query_budget(self):
        self.assert_growth("/api/achievements/summary/")

    def test_earned_list_distinct_selector_query_budget(self):
        self.assert_growth("/api/badges/earned/", earned=True)

    def test_earned_summary_distinct_selector_query_budget(self):
        self.assert_growth("/api/achievements/summary/", earned=True)

    def test_large_catalog_uses_bounded_batches_across_compound_select_limits(self):
        for kind in ("category_projects", "category_mastery"):
            self.add_goals(kind, 0, 210)
        count, queries = self.measured(lambda: visible_badges(Badge.objects.all(), self.child).count())
        self.assertEqual(count, 420)
        self.assertLessEqual(queries, 9)

    def test_standalone_helper_never_reads_the_badge_catalog_and_rechecks_sources(self):
        row = self.badge("category_mastery", "Original")
        def read():
            with CaptureQueriesContext(connection) as queries:
                result = badge_goal_is_available(row, self.child)
            self.assertFalse([q["sql"] for q in queries if '"achievements_badge"' in q["sql"]])
            return result
        self.assertTrue(read())
        first = SkillCategory.objects.create(name="Renamed original")
        self.source(first, {"name": "Original"})
        SkillCategory.objects.create(name="Original")
        self.assertFalse(read())

    def source(self, category, lookup, marker=None):
        return RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category.pk,
            family=self.parent.family, source_lookup=lookup,
            values={"_authoring": marker if marker is not None else {"version": 1, "source": "mcp"}})

    def test_batch_matches_database_native_case_and_exact_source_oracles(self):
        for name in ("Practice", "PRACTICE", "straße", "STRASSE", "é", "É", "100%_", 'Quote " slash \\'):
            category = SkillCategory.objects.create(name=name)
            self.source(category, {"name": name})
        for index, lookup in enumerate(({"name": "Old"}, {"name": "OLD"}, {"name": "Practice", "extra": 1},
                {"name": ["Practice"]}, {"name": None})):
            category = SkillCategory.objects.create(name=f"Renamed {index}")
            self.source(category, lookup)
        untrusted = SkillCategory.objects.create(name="Untrusted")
        self.source(untrusted, {"name": "Practice"}, {"version": 2, "source": "mcp"})
        rows = [self.badge(kind, name) for kind in ("category_projects", "category_mastery")
            for name in ("Practice", "practice", "PRACTICE", "straße", "STRASSE", "é", "É", "100%_", 'Quote " slash \\', "Old", "old", "Missing")]
        expected = {row.pk: not (project_category_resolution(row.criteria_value["category"]).ambiguous
            if row.criteria_type == "category_projects" else len(source_identity_matches(SkillCategory,
                {"name": row.criteria_value["category"]})) > 1) for row in rows}
        context = BadgeGoalAvailability(self.child)
        self.measured(lambda: list(visible_badges(Badge.objects.all(), self.child, availability=context)))
        actual, _count = self.measured(lambda: {row.pk: context.is_available(row) for row in rows})
        self.assertEqual(actual, expected)
        with self.assertNumQueries(0):
            self.assertEqual({row.pk: context.is_available(row) for row in rows}, expected)
        # A context is a completed read snapshot; a new standalone call refreshes.
        missing = next(row for row in rows if row.criteria_type == "category_projects" and row.criteria_value["category"] == "Missing")
        first = SkillCategory.objects.create(name="Moved missing")
        self.source(first, {"name": "Missing"})
        SkillCategory.objects.create(name="MISSING")
        self.assertTrue(context.is_available(missing))
        self.assertFalse(badge_goal_is_available(missing, self.child))
        unsaved = deepcopy(missing)
        unsaved.criteria_value = {"category": "Another missing", "count": 1}
        self.assertTrue(context.is_available(unsaved))

    def test_project_overflow_and_nonpositive_counts_keep_native_semantics(self):
        current = SkillCategory.objects.create(name="Overflow")
        self.source(current, {"name": "Overflow"})
        RPGContentOverride.objects.bulk_create([RPGContentOverride(model_label="achievements.skillcategory",
            object_id=10000 + index, family=self.parent.family, source_lookup={"name": "Overflow", "extra": index},
            values={"_authoring": {"version": 1, "source": "mcp"}}) for index in range(1001)])
        positive = self.badge("category_projects", "Overflow")
        zero = self.badge("category_projects", "Overflow")
        zero.criteria_value["count"] = False
        zero.save()
        mastery = self.badge("category_mastery", "Overflow")
        self.assertTrue(project_category_resolution("Overflow").ambiguous)
        context = BadgeGoalAvailability(self.child)
        self.assertFalse(context.is_available(positive))
        self.assertTrue(context.is_available(zero))
        self.assertTrue(context.is_available(mastery))
        self.assertEqual(set(visible_badges(Badge.objects.all(), self.child).values_list("pk", flat=True)), {zero.pk, mastery.pk})
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [zero])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        # Invalid rows still consume the bound, while the current row's own
        # provenance was excluded before applying it. Exactly1,000 is allowed.
        RPGContentOverride.objects.get(source_lookup__extra=1000).delete()
        self.assertFalse(project_category_resolution("Overflow").ambiguous)
        fresh = BadgeGoalAvailability(self.child)
        list(visible_badges(Badge.objects.all(), self.child, availability=fresh))
        self.assertTrue(fresh.is_available(positive))

    def test_batched_visibility_preserves_actual_native_once_only_awards(self):
        category = SkillCategory.objects.create(name="Current practice")
        self.source(category, {"name": "Original practice"})
        skill = Skill.objects.create(name="Batch practice", category=category)
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=1000, level=6, unlocked=True)
        Project.objects.create(title="Batch completed", assigned_to=self.child, created_by=self.parent,
            category=category, status="completed")
        rows = [self.badge(kind, "Original practice") for kind in ("category_projects", "category_mastery")]
        self.assertEqual(set(visible_badges(Badge.objects.all(), self.child)), set(rows))
        self.assertEqual(set(BadgeService.evaluate_badges(self.child)), set(rows))
        self.assertEqual(BadgeService.evaluate_badges(self.child), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child).count(), 2)
