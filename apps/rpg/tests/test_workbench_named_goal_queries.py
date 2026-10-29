"""Native editor reads batch named goals without changing their saved rules."""
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rewards.models import Reward
from apps.rpg.models import ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


ROOT = "/api/rpg/content-workbench/"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WorkbenchNamedGoalQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        own = make_family("Native named goal editor", parents=[{"username": "native-named-parent", "is_staff": True}])
        foreign = make_family("Other native editor", parents=[{"username": "native-named-other", "is_staff": True}])
        cls.parent, cls.other = own.parents[0], foreign.parents[0]

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def goals(self, start, stop, *, quests=False):
        SkillCategory.objects.bulk_create([SkillCategory(name=f"Native category {index:04d}") for index in range(start, stop)])
        badges = Badge.objects.bulk_create([Badge(name=f"Native badge {index:04d}",
            criteria_type="category_mastery" if quests or index % 2 else "category_projects",
            criteria_value={"category": f"Native category {index:04d}",
                **({"min_level": 1} if quests or index % 2 else {"count": 1})},
            xp_bonus=0, award_coins=False) for index in range(start, stop)])
        if quests:
            QuestDefinition.objects.bulk_create([QuestDefinition(name=f"Native quest {start + offset:04d}",
                quest_type="collection", target_value=1, is_system=True, required_badge=badge,
                trigger_filter={"allowed_triggers": ["chore_complete"]}) for offset, badge in enumerate(badges)])
        return badges

    def badge(self, kind, category, *, level=1):
        return Badge.objects.create(name=f"Native saved badge {Badge.objects.count()}", criteria_type=kind,
            criteria_value={"category": category, **({"count": 1} if kind == "category_projects" else {"min_level": level})},
            xp_bonus=0, award_coins=False)

    def source(self, category, name):
        return RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category.pk,
            family=self.parent.family, source_lookup={"name": name}, values={"_authoring": {"version": 1, "source": "mcp"}})

    def measured(self):
        # Native editor metadata deliberately includes the actor's family shop.
        # Assert read-only behavior, without pretending this entire endpoint is household-free.
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(ROOT)
        self.assertEqual(response.status_code, 200, response.content)
        sql = [query["sql"] for query in queries]
        self.assertFalse([query for query in sql if query.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))])
        return response.json(), sql

    def source_queries(self, sql):
        return [query for query in sql if f'"{RPGContentOverride._meta.db_table}"' in query]

    def test_rest_badge_query_budget_is_constant_from_10_to_100_named_goals(self):
        self.goals(0, 10)
        self.measured()
        small, small_sql = self.measured()
        self.goals(10, 100)
        large, large_sql = self.measured()
        self.assertEqual((len(small["catalog"]["badges"]), len(large["catalog"]["badges"])), (10, 100))
        self.assertTrue(all(row["available_for_new_user"] for row in large["catalog"]["badges"]))
        self.assertEqual(large["audits"]["findings"], [])
        self.assertLessEqual(len(large_sql), len(small_sql),
            f"The bounded editor page must share selector batches: {len(small_sql)} to {len(large_sql)} queries")

    def test_rest_required_badges_share_a_bounded_selector_budget(self):
        self.goals(0, 10, quests=True)
        self.measured()
        small, small_sql = self.measured()
        self.goals(10, 100, quests=True)
        large, large_sql = self.measured()
        self.assertEqual((len(small["catalog"]["quests"]), len(large["catalog"]["quests"])), (10, 100))
        self.assertTrue(all(row["available_for_new_user"] for row in large["catalog"]["quests"]))
        self.assertEqual(large["audits"]["findings"], [])
        counts = {"small": len(self.source_queries(small_sql)), "large": len(self.source_queries(large_sql))}
        # Other native quest checks predate this fix; isolate named identity reads.
        self.assertLessEqual(counts["large"], counts["small"], f"Named prerequisite queries grew: {counts}")
        self.assertLessEqual(counts["large"], 7)

    def test_real_rest_preserves_native_availability_and_raw_legacy_criteria(self):
        renamed = SkillCategory.objects.create(name="Moved native category")
        self.source(renamed, "Original native category")
        SkillCategory.objects.create(name="Original native category")
        rows = [self.badge(kind, name) for kind in ("category_mastery", "category_projects")
            for name in ("Original native category", "Missing native category")]
        rows += [self.badge("category_mastery", "Missing native category", level=level)
                 for level in ("2", 3.9, 0, False, 6.9, 7.1, "broken")]
        expected = {row.pk: badge_goal_is_available(row) for row in rows}
        self.assertIn(False, expected.values())
        self.assertIn(True, expected.values())
        body, _sql = self.measured()
        actual = {row["id"]: row for row in body["catalog"]["badges"]}
        self.assertEqual({pk: row["available_for_new_user"] for pk, row in actual.items()}, expected)
        self.assertEqual({pk: row["criteria_value"] for pk, row in actual.items()}, {row.pk: row.criteria_value for row in rows})
        unreachable = {finding["id"] for finding in body["audits"]["findings"] if finding["code"] == "unreachable_badge"}
        self.assertEqual(unreachable, {pk for pk, available in expected.items() if not available})
        invalid = {finding["id"] for finding in body["audits"]["findings"] if finding["code"] == "invalid_badge_criteria"}
        self.assertIn(rows[4].pk, invalid, "Strict authoring audit still reports native-compatible numeric strings")

    def test_each_rest_read_refreshes_named_prerequisites(self):
        renamed = SkillCategory.objects.create(name="Moved fresh native category")
        self.source(renamed, "Original fresh native category")
        badge = self.badge("category_mastery", "Original fresh native category")
        quest = QuestDefinition.objects.create(name="Fresh native quest", quest_type="collection", target_value=1,
            is_system=True, required_badge=badge, trigger_filter={"allowed_triggers": ["chore_complete"]})
        before, _sql = self.measured()
        competing = SkillCategory.objects.create(name="Original fresh native category")
        after, _sql = self.measured()
        self.assertTrue(before["catalog"]["badges"][0]["available_for_new_user"])
        self.assertTrue(before["catalog"]["quests"][0]["available_for_new_user"])
        self.assertFalse(after["catalog"]["badges"][0]["available_for_new_user"])
        self.assertFalse(after["catalog"]["quests"][0]["available_for_new_user"])
        self.assertIn((quest.pk, "unreachable_required_badge"),
            {(finding["id"], finding["code"]) for finding in after["audits"]["findings"]})
        competing.delete()
        restored, _sql = self.measured()
        self.assertTrue(restored["catalog"]["badges"][0]["available_for_new_user"])
        self.assertTrue(restored["catalog"]["quests"][0]["available_for_new_user"])

    def test_badge_and_quest_editor_caps_still_fail_before_unbounded_projection(self):
        Badge.objects.bulk_create([Badge(name=f"Capped native badge {index}", criteria_type="category_mastery",
            criteria_value={"category": "Shared capped category", "min_level": 1}, xp_bonus=0, award_coins=False)
            for index in range(512)])
        body, _sql = self.measured()
        self.assertEqual(len(body["catalog"]["badges"]), 512)
        self.badge("category_mastery", "Shared capped category")
        response = self.client.get(ROOT)
        self.assertEqual(response.status_code, 400)
        self.assertIn("badges catalog exceeds the editor limit (512)", response.json()["detail"])
        Badge.objects.all().delete()
        QuestDefinition.objects.bulk_create([QuestDefinition(name=f"Capped native quest {index}", quest_type="collection",
            target_value=1, is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]}) for index in range(256)])
        body, _sql = self.measured()
        self.assertEqual(len(body["catalog"]["quests"]), 256)
        QuestDefinition.objects.create(name="One native quest too many", quest_type="collection", target_value=1,
            is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
        response = self.client.get(ROOT)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quests catalog exceeds the editor limit (256)", response.json()["detail"])

    def test_projection_keeps_values_editability_and_own_family_shop_uses(self):
        item = ItemDefinition.objects.create(slug="native-editable-food", name="Native food", item_type="food")
        RPGContentOverride.objects.create(model_label="rpg.itemdefinition", object_id=item.pk,
            family=self.other.family, source_lookup={"slug": item.slug}, values={"name": item.name})
        offer = Reward.objects.create(family=self.parent.family, name="Own native offer", cost_coins=7,
            item_definition=item, fulfillment_kind="digital_item")
        Reward.objects.create(family=self.other.family, name="Foreign native offer", cost_coins=9,
            item_definition=item, fulfillment_kind="digital_item")
        badge = self.badge("category_mastery", "Native editable missing category")
        quest = QuestDefinition.objects.create(name="Editable native quest", quest_type="collection", target_value=2,
            is_system=True, required_badge=badge, trigger_filter={"allowed_triggers": ["chore_complete"]})
        body, _sql = self.measured()
        projected_item = body["catalog"]["items"][0]
        self.assertEqual(projected_item["values"]["name"], item.name)
        self.assertFalse(projected_item["editable"])
        self.assertTrue(projected_item["has_database_override"])
        self.assertEqual(projected_item["used_by"]["shop_offers"], [{"id": offer.pk, "name": offer.name,
            "cost_coins": 7, "is_active": True}])
        projected_quest = body["catalog"]["quests"][0]
        self.assertEqual((projected_quest["id"], projected_quest["values"]["required_badge"]), (quest.pk, badge.pk))
        self.assertEqual(projected_quest["values"]["target_value"], 2)
        self.assertTrue(projected_quest["editable"])
        self.assertTrue(projected_quest["available_for_new_user"])
