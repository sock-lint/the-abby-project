"""Progression Lab snapshots batch modeled global selectors within existing caps."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, SkillCategory, SkillProgress, UserBadge
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, RPGContentOverride, UserInventory
from apps.rpg.progression.catalog import snapshot_catalog
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionNamedGoalQueryTests(TestCase):
    def goals(self, start, stop, kind="category_mastery"):
        SkillCategory.objects.bulk_create([SkillCategory(name=f"Snapshot category {index:04d}") for index in range(start, stop)])
        Badge.objects.bulk_create([Badge(name=f"Snapshot badge {index:04d}", criteria_type=kind,
            criteria_value={"category": f"Snapshot category {index:04d}",
                **({"count": 1} if kind == "category_projects" else {"min_level": 1})},
            xp_bonus=0, award_coins=False) for index in range(start, stop)])

    def measured(self):
        with CaptureQueriesContext(connection) as queries:
            catalog = snapshot_catalog()
        sql = [row["sql"] for row in queries]
        self.assertFalse([query for query in sql if query.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))])
        for model in (get_user_model(), SkillProgress, UserBadge, CoinLedger, CharacterProfile, UserInventory):
            self.assertFalse([query for query in sql if f'"{model._meta.db_table}"' in query], model._meta.label)
        return catalog, sql

    def test_full_512_badge_snapshot_uses_100_selector_chunks(self):
        _catalog, empty = self.measured()
        self.goals(0, 100)
        small, small_sql = self.measured()
        self.assertEqual(len(small.badges), 100)
        self.assertLessEqual(len(small_sql), len(empty) + 1)
        self.goals(100, 512)
        full, full_sql = self.measured()
        self.assertEqual(len(full.badges), 512)
        self.assertLessEqual(len(full_sql), len(empty) + 6)
        self.assertLessEqual(len(full_sql), len(small_sql) + 5)
        with self.assertNumQueries(0):
            self.assertEqual(full.summary()["modeled_badges"], 512)
            self.assertEqual([row.criteria_value["min_level"] for row in full.badges], [1] * 512)
        self.goals(512, 513)
        with self.assertRaisesRegex(ValueError, r"badge catalog exceeds.*512"):
            snapshot_catalog()

    def test_unmodeled_goals_do_not_trigger_named_selector_queries(self):
        _catalog, empty = self.measured()
        self.goals(0, 512, "category_projects")
        catalog, sql = self.measured()
        self.assertEqual(catalog.badges, ())
        self.assertEqual(catalog.excluded_badges, {"category_projects": 512})
        self.assertEqual(len(sql), len(empty))

    def test_snapshot_availability_refreshes_but_previous_snapshot_stays_detached(self):
        family = make_family("Snapshot sources", parents=[{"username": "snapshot-source-parent"}])
        original = SkillCategory.objects.create(name="Renamed snapshot category")
        RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=original.pk,
            family=family.family, source_lookup={"name": "Original snapshot category"},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        badge = Badge.objects.create(name="Retained snapshot mastery", criteria_type="category_mastery",
            criteria_value={"category": "Original snapshot category", "min_level": "1"}, xp_bonus=0, award_coins=False)
        self.assertTrue(badge_goal_is_available(badge))
        before, _ = self.measured()
        self.assertEqual([row.pk for row in before.badges], [badge.pk])
        competing = SkillCategory.objects.create(name="Original snapshot category")
        after, _ = self.measured()
        self.assertEqual(after.badges, ())
        self.assertEqual(after.excluded_badges, {"category_mastery": 1})
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        with self.assertNumQueries(0):
            self.assertEqual([row.pk for row in before.badges], [badge.pk])
        competing.delete()
        restored, _ = self.measured()
        self.assertEqual([row.pk for row in restored.badges], [badge.pk])
        self.assertEqual(before.fingerprint, restored.fingerprint)
