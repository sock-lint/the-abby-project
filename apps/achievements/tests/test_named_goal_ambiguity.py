"""Named goal availability shares native category ambiguity without changing payouts."""
from copy import deepcopy

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.availability import BadgeGoalAvailability, badge_goal_is_available
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, RPGContentOverride, UserInventory
from apps.rpg.progression.catalog import snapshot_catalog
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], ALLOWED_HOSTS=["testserver"])
class NamedGoalAmbiguityTests(TestCase):
    def setUp(self):
        cache.clear()
        home = make_family("Named goal ambiguity", parents=[{
            "username": "named-goal-parent", "is_staff": True,
        }], children=[{"username": "named-goal-child"}])
        self.actor, self.child = home.parents[0], home.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.name = "Named practice"

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        result = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", result, result)
        return result

    def category(self, name):
        category = SkillCategory.objects.get(pk=self.wire("create_category", {"name": name})["id"])
        self.populate(category)
        return category

    def populate(self, category):
        skill = Skill.objects.create(category=category, name=f"Named skill {category.pk}")
        SkillProgress.objects.create(user=self.child, skill=skill, level=6, xp_points=1000000, unlocked=True)
        Project.objects.create(title="Completed named project", assigned_to=self.child, created_by=self.actor,
            category=category, status=Project.Status.COMPLETED)

    def rename(self, category, name, **values):
        self.wire("update_category", {"category_id": category.pk, "name": name, **values})
        category.refresh_from_db()

    def retained(self):
        category = self.category(self.name)
        self.rename(category, "Renamed practice")
        return category

    def legacy_category(self, name, *, source_name=None):
        """Saved ambiguity predating the authenticated admission guards."""
        category = SkillCategory.objects.create(name=name)
        RPGContentOverride.objects.create(family=self.actor.family,
            model_label="achievements.skillcategory", object_id=category.pk,
            source_lookup={"name": source_name or name},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        self.populate(category)
        return category

    def tie(self, kind):
        first = self.retained()
        if kind == "category_projects":
            second = self.legacy_category(self.name.upper())
        else:
            # A valid saved current row can predate source-name admission.
            second = SkillCategory.objects.create(name=self.name)
            self.populate(second)
        return first, second

    def badge(self, kind, **values):
        rule = {"category": self.name, **({"count": 1} if kind == "category_projects" else {"min_level": 1})}
        return Badge.objects.create(name=f"Named badge {Badge.objects.count()}", description="Saved category goal",
            criteria_type=kind, criteria_value={**rule, **values}, xp_bonus=0, award_coins=False)

    def assert_catalog(self, badge, available, *, earned=False, mcp_available=None):
        self.assertEqual(badge_goal_is_available(badge, self.child), available)
        response = self.client.get("/api/badges/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()["results"]}
        self.assertEqual(badge.pk in rows, available or earned)
        if badge.pk in rows:
            self.assertEqual(rows[badge.pk]["catalog_available"], available)
        row = next(row for row in self.wire("read_rpg_catalog", {"section": "badges"})["results"]
                   if row["id"] == badge.pk)
        self.assertEqual(row["available_for_new_user"], available if mcp_available is None else mcp_available)
        summary = self.client.get("/api/achievements/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["total_badges"], int(available or earned))
        catalog = snapshot_catalog()
        # Project-completion badges are explicitly outside the Lab's modeled
        # criteria. Mastery's availability must also govern its detached input.
        included = badge.pk in {row.pk for row in catalog.badges}
        self.assertEqual(included, available and badge.criteria_type == "category_mastery")

    def test_project_retained_current_tie_is_unavailable(self):
        self.tie("category_projects")
        badge = self.badge("category_projects")
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, False)

    def test_mastery_retained_current_tie_is_unavailable(self):
        self.tie("category_mastery")
        badge = self.badge("category_mastery")
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, False)

    def test_project_multiple_retained_tie_is_unavailable(self):
        self.retained()
        self.legacy_category("Other renamed practice", source_name=self.name.upper())
        badge = self.badge("category_projects")
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, False)

    def test_mastery_multiple_retained_tie_is_unavailable(self):
        self.retained()
        second = self.category("Other original practice")
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=second.pk)
        source.source_lookup = {"name": self.name}
        source.save(update_fields=["source_lookup"])
        badge = self.badge("category_mastery")
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, False)

    def test_earned_tied_goal_remains_in_catalog_and_history_without_read_side_effects(self):
        self.tie("category_mastery")
        badge = self.badge("category_mastery")
        UserBadge.objects.create(user=self.child, badge=badge)
        before = {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in
                  (Badge, UserBadge, SkillProgress, CoinLedger, UserInventory, DropLog)}
        with CaptureQueriesContext(connection) as queries:
            self.assert_catalog(badge, False, earned=True)
            response = self.client.get("/api/badges/earned/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["badge"]["id"] for row in response.json()["results"]], [badge.pk])
        self.assertFalse(response.json()["results"][0]["badge"]["catalog_available"])
        after = {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in
                 (Badge, UserBadge, SkillProgress, CoinLedger, UserInventory, DropLog)}
        self.assertEqual(after, before)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))

    def test_current_project_union_is_available_including_own_source_overrides(self):
        self.category(self.name)
        self.category(self.name.upper())
        badge = self.badge("category_projects", count=2)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)

    def test_mastery_keeps_exact_case_when_current_names_differ_only_by_case(self):
        self.category(self.name)
        self.category(self.name.upper())
        badge = self.badge("category_mastery")
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)

    def test_unique_retained_mastery_remains_available_after_retirement(self):
        original = self.retained()
        self.wire("update_category", {"category_id": original.pk, "is_retired": True})
        badge = self.badge("category_mastery")
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)

    def test_project_tie_retirement_keeps_ambiguity_but_renameback_restores_union(self):
        original, competing = self.tie("category_projects")
        badge = self.badge("category_projects")
        self.assert_catalog(badge, False)
        self.wire("update_category", {"category_id": competing.pk, "is_retired": True})
        self.assert_catalog(badge, False)
        self.rename(original, self.name)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)

    def test_explicit_mastery_selector_repair_recovers_without_replaying_an_earned_badge(self):
        original, _other = self.tie("category_mastery")
        badge = self.badge("category_mastery")
        self.assert_catalog(badge, False)
        self.wire("update_badge", {"badge_id": badge.pk,
            "criteria_value": {"category": original.name, "min_level": 1}})
        badge.refresh_from_db()
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)

    def test_project_tie_nonpositive_counts_preserve_native_vacuous_awards(self):
        self.tie("category_projects")
        for count in (0, -1, -0.5, False):
            with self.subTest(count=count):
                badge = self.badge("category_projects", count=count)
                self.assertTrue(BadgeService._check_criteria(self.child, badge))
                self.assert_catalog(badge, True, mcp_available=False)
                self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
                self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
                badge.delete()

    def test_plural_project_selector_ignores_a_tied_named_selector(self):
        self.tie("category_projects")
        badge = self.badge("category_projects", categories=2, count=100)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_catalog(badge, True)

    def test_absent_and_null_project_selectors_keep_uncategorized_semantics(self):
        Project.objects.create(title="Saved uncategorized project", assigned_to=self.child,
            created_by=self.actor, category=None, status=Project.Status.COMPLETED)
        for explicit_null in (False, True):
            badge = self.badge("category_projects")
            if explicit_null:
                badge.criteria_value["category"] = None
            else:
                del badge.criteria_value["category"]
            badge.save(update_fields=["criteria_value"])
            self.assertTrue(BadgeService._check_criteria(self.child, badge))
            self.assert_catalog(badge, True, mcp_available=not explicit_null)
            badge.delete()

    def test_preexisting_missing_name_policy_is_unchanged(self):
        for kind in ("category_projects", "category_mastery"):
            badge = self.badge(kind, category="No such category")
            self.assertFalse(BadgeService._check_criteria(self.child, badge))
            self.assert_catalog(badge, True)
            badge.delete()

    def test_read_context_cache_reuses_resolution_but_new_context_sees_source_changes(self):
        original = self.retained()
        badge = self.badge("category_mastery")
        context = BadgeGoalAvailability(self.child)
        self.assertTrue(context.is_available(badge))
        with CaptureQueriesContext(connection) as queries:
            for _ in range(10):
                self.assertTrue(context.is_available(badge))
        self.assertEqual(len(queries), 0)
        competing = SkillCategory.objects.create(name=self.name)
        self.populate(competing)
        self.assertTrue(context.is_available(badge))  # Same completed read snapshot.
        self.assertFalse(badge_goal_is_available(badge, self.child))
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assertEqual(original.name, "Renamed practice")

    def test_cache_keys_preserve_kind_and_exact_mastery_selector(self):
        self.tie("category_projects")
        project = self.badge("category_projects")
        mastery = self.badge("category_mastery")
        context = BadgeGoalAvailability(self.child)
        self.assertFalse(context.is_available(project))
        self.assertTrue(context.is_available(mastery))
        # Exact original spelling has a retained/current mastery tie; a
        # different-case current spelling remains a separate literal selector.
        exact = SkillCategory.objects.create(name=self.name)
        self.populate(exact)
        context = BadgeGoalAvailability(self.child)
        self.assertFalse(context.is_available(mastery))
        upper = deepcopy(mastery)
        upper.criteria_value = {**mastery.criteria_value, "category": self.name.upper()}
        self.assertTrue(context.is_available(upper))

    def test_dangling_inexact_and_untrusted_sources_do_not_create_false_ties(self):
        self.category(self.name)
        other = self.category("Unrelated practice")
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=other.pk)
        for lookup, values, object_id in (
            ({"name": self.name}, {"_authoring": {"version": 2, "source": "mcp"}}, other.pk),
            ({"name": self.name, "extra": True}, {"_authoring": {"version": 1, "source": "mcp"}}, other.pk),
            ({"name": self.name}, {"_authoring": {"version": 1, "source": "mcp"}}, other.pk + 10000),
        ):
            source.source_lookup, source.values, source.object_id = lookup, values, object_id
            source.save(update_fields=["source_lookup", "values", "object_id"])
            badge = self.badge("category_mastery")
            self.assertTrue(BadgeService._check_criteria(self.child, badge))
            self.assert_catalog(badge, True)
            badge.delete()
