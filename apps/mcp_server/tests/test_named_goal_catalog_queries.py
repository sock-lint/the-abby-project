"""Global MCP pages batch only their selected named badge prerequisites."""

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, SkillCategory, SkillProgress, UserBadge
from apps.mcp_server.catalog import catalog_row
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.models import QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, RPGContentOverride, UserInventory
from config.tests.factories import make_family


TOOLS = ("read_rpg_catalog", "audit_rpg_catalog", "get_content_workbench")
GLOBAL_SCOPES = frozenset({"mcp:catalog", "mcp:author"})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NamedGoalCatalogQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        home = make_family("Named catalog pages", parents=[{"username": "named-page-parent", "is_staff": True}],
            children=[{"username": "named-page-child"}])
        other = make_family("Other named pages", parents=[{"username": "named-page-other", "is_staff": True}])
        cls.parent, cls.child, cls.other = home.parents[0], home.children[0], other.parents[0]

    def badge(self, kind, name):
        return Badge.objects.create(name=f"Named badge {Badge.objects.count():04d}", criteria_type=kind,
            criteria_value={"category": name, **({"count": 1} if kind == "category_projects" else {"min_level": 1})},
            xp_bonus=0, award_coins=False)

    def goals(self, start, stop, *, quests=False):
        rows = []
        for index in range(start, stop):
            name = f"Selected category {index:04d}"
            SkillCategory.objects.get_or_create(name=name)
            row = self.badge("category_mastery" if quests or index % 2 else "category_projects", name)
            rows.append(row)
            if quests:
                QuestDefinition.objects.create(name=f"Selected quest {index:04d}", quest_type="collection",
                    target_value=1, is_system=True, required_badge=row,
                    trigger_filter={"allowed_triggers": ["chore_complete"]})
        return rows

    def source(self, category, lookup, *, marker=None):
        return RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category.pk,
            family=self.parent.family, source_lookup=lookup,
            values={"_authoring": {"version": 1, "source": "mcp"} if marker is None else marker})

    def call(self, tool, section="badges", *, actor=None, **page):
        with override_user(actor or self.parent, scopes=GLOBAL_SCOPES):
            result = async_to_sync(mcp.call_tool)(tool, {"params": {"section": section, **page}})
        body = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", body)
        return body

    def measured(self, read):
        with CaptureQueriesContext(connection) as queries:
            result = read()
        sql = [row["sql"] for row in queries]
        self.assertFalse([query for query in sql if query.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))])
        for model in (get_user_model(), SkillProgress, UserBadge, CoinLedger, CharacterProfile, UserInventory):
            self.assertFalse([query for query in sql if f'"{model._meta.db_table}"' in query], model._meta.label)
        return result, sql

    def selector_queries(self, sql):
        return [query for query in sql if f'"{RPGContentOverride._meta.db_table}"' in query]

    def test_registered_badge_pages_have_constant_queries_through_limit_100(self):
        self.goals(0, 10)
        small = {tool: self.measured(lambda: self.call(tool, limit=100))[1] for tool in TOOLS}
        self.goals(10, 100)
        for tool in TOOLS:
            with self.subTest(tool=tool):
                body, queries = self.measured(lambda: self.call(tool, limit=100))
                self.assertEqual(body["total"], 100)
                self.assertIsNone(body["next_after"])
                if tool == "audit_rpg_catalog":
                    self.assertEqual((body["checked"], body["findings"]), (100, []))
                else:
                    self.assertEqual(len(body["results"]), 100)
                    self.assertTrue(all(row["available_for_new_user"] for row in body["results"]))
                self.assertLessEqual(len(queries), len(small[tool]))
                self.assertLessEqual(len(queries), 4, f"{tool} must batch the two native selector kinds")

    def test_registered_quest_pages_batch_actual_required_badges(self):
        rows = self.goals(0, 100, quests=True)
        for tool in TOOLS:
            with self.subTest(tool=tool):
                body, queries = self.measured(lambda: self.call(tool, "quests", limit=100))
                if tool == "audit_rpg_catalog":
                    self.assertEqual((body["checked"], body["findings"]), (100, []))
                else:
                    self.assertEqual(len(body["results"]), 100)
                    self.assertTrue(all(row["available_for_new_user"] for row in body["results"]))
                self.assertLessEqual(len(self.selector_queries(queries)), 1,
                    "Unrelated existing quest checks must not repeat named prerequisite resolution")
        self.source(SkillCategory.objects.create(name="Competing renamed prerequisite"),
            {"name": rows[0].criteria_value["category"]})
        first_quest = QuestDefinition.objects.order_by("pk").first()
        for tool in TOOLS:
            body, queries = self.measured(lambda: self.call(tool, "quests", limit=1))
            self.assertEqual(len(self.selector_queries(queries)), 1)
            self.assertNotIn(rows[1].criteria_value["category"], self.selector_queries(queries)[0])
            if tool == "audit_rpg_catalog":
                self.assertEqual([(finding["id"], finding["code"]) for finding in body["findings"]],
                    [(first_quest.pk, "unreachable_required_badge")])
            else:
                self.assertFalse(body["results"][0]["available_for_new_user"])

    def test_pages_do_not_resolve_the_sentinel_or_other_catalog_selectors(self):
        first = self.badge("category_mastery", "First page only")
        later = self.badge("category_projects", "Off-page sentinel")
        self.goals(0, 105)
        for tool in TOOLS:
            with self.subTest(tool=tool):
                body, sql = self.measured(lambda: self.call(tool, limit=1))
                self.assertEqual((body["total"], body["next_after"]), (107, first.pk))
                selectors = self.selector_queries(sql)
                self.assertEqual(len(selectors), 1)
                self.assertNotIn("Off-page sentinel", selectors[0])
                self.assertNotIn("Selected category", selectors[0])
                second, sql = self.measured(lambda: self.call(tool, after=first.pk, limit=1))
                self.assertEqual(second["next_after"], later.pk)
                self.assertNotIn("First page only", " ".join(self.selector_queries(sql)))

    def test_batch_preserves_literal_database_identity_semantics(self):
        names = ("Practice", "PRACTICE", "straße", "STRASSE", "é", "É", "100%_", 'Quote " slash \\')
        for name in names:
            category = SkillCategory.objects.create(name=name)
            self.source(category, {"name": name})
        for index, lookup in enumerate(({"name": "Old"}, {"name": "OLD"}, {"name": "Practice", "extra": 1},
                {"name": ["Practice"]}, {"name": None})):
            self.source(SkillCategory.objects.create(name=f"Moved {index}"), lookup)
        self.source(SkillCategory.objects.create(name="Untrusted"), {"name": "Practice"},
            marker={"version": True, "source": "mcp"})
        rows = [self.badge(kind, name) for kind in ("category_projects", "category_mastery")
            for name in (*names, "practice", "Old", "old", "Missing")]
        expected = {row.pk: badge_goal_is_available(row) for row in rows}
        self.assertIn(False, expected.values())
        self.assertIn(True, expected.values())
        for tool in ("read_rpg_catalog", "get_content_workbench"):
            body, _ = self.measured(lambda: self.call(tool, limit=100))
            self.assertEqual({row["id"]: row["available_for_new_user"] for row in body["results"]}, expected)
        body, _ = self.measured(lambda: self.call("audit_rpg_catalog", limit=100))
        self.assertEqual({finding["id"] for finding in body["findings"] if finding["code"] == "unreachable_badge"},
            {pk for pk, available in expected.items() if not available})

    def test_project_source_bound_is_applied_before_filtering_invalid_rows(self):
        category = SkillCategory.objects.create(name="Overflow")
        self.source(category, {"name": "Overflow"})
        RPGContentOverride.objects.bulk_create([RPGContentOverride(model_label="achievements.skillcategory",
            object_id=10000 + index, family=self.parent.family, source_lookup={"name": "Overflow", "extra": index},
            values={"_authoring": {"version": 1, "source": "mcp"}}) for index in range(1001)])
        project = self.badge("category_projects", "Overflow")
        mastery = self.badge("category_mastery", "Overflow")
        for tool in ("read_rpg_catalog", "get_content_workbench"):
            body, _ = self.measured(lambda: self.call(tool, limit=100))
            self.assertEqual({row["id"]: row["available_for_new_user"] for row in body["results"]},
                {project.pk: False, mastery.pk: True})
        RPGContentOverride.objects.get(source_lookup__extra=1000).delete()
        body, _ = self.measured(lambda: self.call("read_rpg_catalog", limit=100))
        self.assertTrue(all(row["available_for_new_user"] for row in body["results"]))

    def test_new_reads_refresh_global_sources_without_changing_earned_history(self):
        original = SkillCategory.objects.create(name="Renamed original")
        self.source(original, {"name": "Original"})
        row = self.badge("category_mastery", "Original")
        earned = UserBadge.objects.create(user=self.child, badge=row)
        for tool in TOOLS:
            body, _ = self.measured(lambda: self.call(tool))
            if tool == "audit_rpg_catalog":
                self.assertEqual(body["findings"], [])
            else:
                self.assertTrue(body["results"][0]["available_for_new_user"])
        competing = SkillCategory.objects.create(name="Original")
        for actor in (self.parent, self.other):
            for tool in TOOLS:
                body, _ = self.measured(lambda: self.call(tool, actor=actor))
                if tool == "audit_rpg_catalog":
                    self.assertEqual([finding["code"] for finding in body["findings"]], ["unreachable_badge"])
                else:
                    self.assertFalse(body["results"][0]["available_for_new_user"])
        client = APIClient()
        client.force_authenticate(self.child)
        history = client.get("/api/badges/earned/").json()["results"]
        self.assertEqual([entry["badge"]["id"] for entry in history], [row.pk])
        self.assertFalse(history[0]["badge"]["catalog_available"])
        self.assertEqual(UserBadge.objects.get(pk=earned.pk).badge_id, row.pk)
        competing.delete()
        body, _ = self.measured(lambda: self.call("read_rpg_catalog"))
        self.assertTrue(body["results"][0]["available_for_new_user"])

    def test_standalone_projection_rechecks_only_its_requested_selector(self):
        original = SkillCategory.objects.create(name="Renamed standalone category")
        self.source(original, {"name": "Standalone original"})
        row = self.badge("category_mastery", "Standalone original")
        for competing in (False, True):
            if competing:
                SkillCategory.objects.create(name="Standalone original")
            result, sql = self.measured(lambda: catalog_row("badges", row))
            self.assertEqual(result["available_for_new_user"], not competing)
            self.assertFalse([query for query in sql if f'"{Badge._meta.db_table}"' in query])
            self.assertEqual(badge_goal_is_available(row), not competing)

