"""Retained dangling taxonomy history cannot consume live Lab source capacity."""
from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory
from apps.rpg.models import RPGContentOverride
from apps.rpg.progression import catalog, experiments


class ProgressionDanglingOverrideLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        RPGContentOverride.objects.bulk_create([
            RPGContentOverride(
                model_label="achievements.skill", object_id=1000000 + index,
                source_lookup={"name": f"x{index}", "category_id": 1},
                values={"_authoring": {"version": 1, "source": "mcp"}},
            ) for index in range(4097)
        ])

    def available(self, function):
        try:
            return function()
        except ValueError as error:
            self.fail(f"Dangling taxonomy history made the live catalog unavailable: {error}")

    def retain(self, obj, lookup):
        return RPGContentOverride.objects.create(
            model_label=obj._meta.label_lower, object_id=obj.pk, source_lookup=lookup,
            values={"_authoring": {"version": 1, "source": "mcp"}},
        )

    def test_snapshot_ignores_more_than_4096_dangling_source_records(self):
        saved_ids = list(RPGContentOverride.objects.values_list("pk", flat=True))
        snapshot = self.available(catalog.snapshot_catalog)
        self.assertEqual(dict(snapshot.source_categories), {})
        self.assertEqual(dict(snapshot.source_skills), {})
        self.assertEqual(list(RPGContentOverride.objects.values_list("pk", flat=True)), saved_ids)

    def test_freshness_token_ignores_dangling_history_and_its_edits(self):
        before = self.available(experiments._catalog_source_token)
        RPGContentOverride.objects.filter(object_id=1000000).update(
            source_lookup={"name": "Changed historical source", "category_id": 123},
        )
        self.assertEqual(self.available(experiments._catalog_source_token), before)

    def test_live_retired_renamed_sources_remain_resolvable_alongside_history(self):
        category = SkillCategory.objects.create(name="Renamed category", is_retired=True)
        skill = Skill.objects.create(category=category, name="Renamed skill", is_retired=True)
        self.retain(category, {"name": "Original category"})
        self.retain(skill, {"name": "Original skill", "category_id": category.pk})
        snapshot = self.available(catalog.snapshot_catalog)
        self.assertEqual(snapshot.source_categories["Original category"], category.pk)
        self.assertEqual(snapshot.source_skills[(category.pk, "Original skill")], skill.pk)
        self.assertEqual(RPGContentOverride.objects.count(), 4099)
        self.available(experiments._catalog_source_token)

    def test_object_ids_only_admit_sources_for_the_matching_taxonomy_model(self):
        category = SkillCategory.objects.create(pk=7001, name="Current category")
        skill = Skill.objects.create(pk=8001, category=category, name="Current skill")
        RPGContentOverride.objects.bulk_create([
            RPGContentOverride(model_label="achievements.skill", object_id=category.pk,
                source_lookup={"name": "Wrong skill identity", "category_id": category.pk},
                values={"_authoring": {"version": 1, "source": "mcp"}}),
            RPGContentOverride(model_label="achievements.skillcategory", object_id=skill.pk,
                source_lookup={"name": "Wrong category identity"},
                values={"_authoring": {"version": 1, "source": "mcp"}}),
        ])
        snapshot = self.available(catalog.snapshot_catalog)
        self.assertNotIn("Wrong category identity", snapshot.source_categories)
        self.assertNotIn((category.pk, "Wrong skill identity"), snapshot.source_skills)
        self.assertFalse(catalog.taxonomy_source_overrides().exists())

    def test_reappearing_exact_object_enters_both_snapshot_and_freshness(self):
        before = self.available(experiments._catalog_source_token)
        category = SkillCategory.objects.create(pk=1, name="Source category")
        skill = Skill.objects.create(pk=1000000, category=category, name="New display name")
        snapshot = self.available(catalog.snapshot_catalog)
        self.assertEqual(snapshot.source_skills[(category.pk, "x0")], skill.pk)
        self.assertNotEqual(self.available(experiments._catalog_source_token), before)
        self.assertEqual(list(catalog.taxonomy_source_overrides().values_list("object_id", flat=True)), [skill.pk])
        self.assertEqual(RPGContentOverride.objects.count(), 4097)

    def test_live_source_limits_still_fail_closed(self):
        category = SkillCategory.objects.create(name="Current category")
        skill = Skill.objects.create(category=category, name="Current skill")
        self.retain(category, {"name": "Original category"})
        self.retain(skill, {"name": "Original skill", "category_id": category.pk})
        with patch.object(catalog, "TAXONOMY_OVERRIDE_LIMIT", 1):
            with self.assertRaisesRegex(ValueError, "taxonomy source catalog exceeds"):
                catalog.snapshot_catalog()
        with patch.dict(experiments._CATALOG_SOURCE_LIMITS, {"rpg.RPGContentOverride": 1}):
            with self.assertRaisesRegex(ValueError, "catalog source exceeds"):
                experiments._catalog_source_token()
