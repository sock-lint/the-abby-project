"""Detached Lab identities match the installed source resolver and stay current."""
from dataclasses import FrozenInstanceError

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.achievements.models import Skill, SkillCategory
from apps.achievements.source_identity import resolve_fixed_skill, resolve_source_identity
from apps.rpg.models import RPGContentOverride
from apps.rpg.progression.catalog import Catalog, snapshot_catalog


class ProgressionTaxonomySnapshotTests(TestCase):
    def setUp(self):
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(category=self.category, name="Reading Comprehension")
        self.other = SkillCategory.objects.create(name="Other practice")

    def retain(self, obj, lookup, *, provenance=None):
        return RPGContentOverride.objects.create(
            model_label=obj._meta.label_lower, object_id=obj.pk, source_lookup=lookup,
            values={"_authoring": provenance if provenance is not None else {"version": 1, "source": "mcp"},
                    "description": "Unrelated private authoring payload"},
        )

    def assert_native_identity(self, catalog, category_name="Language Arts", skill_name="Reading Comprehension"):
        expected_category = resolve_source_identity(SkillCategory, {"name": category_name})
        expected_skill = resolve_fixed_skill(category_name, skill_name)
        category_id = catalog.source_categories.get(category_name)
        self.assertEqual(category_id, expected_category.pk if expected_category else None)
        skill_id = catalog.source_skills.get((category_id, skill_name)) if category_id is not None else None
        self.assertEqual(skill_id, expected_skill.pk if expected_skill else None)
        return skill_id

    def test_category_display_name_change_invalidates_the_catalog(self):
        before = snapshot_catalog().fingerprint
        SkillCategory.objects.filter(pk=self.category.pk).update(name="Language practice")
        self.assertNotEqual(before, snapshot_catalog().fingerprint)

    def test_empty_category_identity_changes_invalidate_the_catalog(self):
        before = snapshot_catalog().fingerprint
        SkillCategory.objects.filter(pk=self.other.pk).update(name="Empty practice renamed")
        self.assertNotEqual(before, snapshot_catalog().fingerprint)

    def test_canonical_source_less_and_unrelated_same_name_skill_match_native(self):
        Skill.objects.create(category=self.other, name=self.skill.name)
        self.assertFalse(RPGContentOverride.objects.exists())
        self.assertEqual(self.assert_native_identity(snapshot_catalog()), self.skill.pk)

    def test_retained_renamed_reparented_retired_source_matches_native(self):
        self.retain(self.category, {"name": self.category.name})
        self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
        SkillCategory.objects.filter(pk=self.category.pk).update(name="Language practice", is_retired=True)
        Skill.objects.filter(pk=self.skill.pk).update(name="Reading understanding", category=self.other, is_retired=True)
        catalog = snapshot_catalog()
        self.assertEqual(self.assert_native_identity(catalog), self.skill.pk)
        self.assertEqual(catalog.source_categories["Language practice"], self.category.pk)
        self.assertEqual(catalog.source_skills[(self.other.pk, "Reading understanding")], self.skill.pk)

    def test_current_and_retained_matches_for_one_object_are_deduplicated(self):
        self.retain(self.category, {"name": self.category.name})
        self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
        self.assertEqual(self.assert_native_identity(snapshot_catalog()), self.skill.pk)

    def test_empty_current_category_namesake_fails_closed(self):
        self.retain(self.category, {"name": self.category.name})
        SkillCategory.objects.filter(pk=self.category.pk).update(name="Language practice")
        SkillCategory.objects.create(name="Language Arts")
        catalog = snapshot_catalog()
        self.assertIsNone(self.assert_native_identity(catalog))
        self.assertIsNone(catalog.source_categories["Language Arts"])

    def test_distinct_retained_skill_namesake_fails_closed(self):
        rogue = Skill.objects.create(category=self.other, name="Different skill")
        self.retain(rogue, {"name": self.skill.name, "category_id": self.category.pk})
        catalog = snapshot_catalog()
        self.assertIsNone(self.assert_native_identity(catalog))
        self.assertIsNone(catalog.source_skills[(self.category.pk, self.skill.name)])

    def test_inexact_provenance_and_partial_or_extra_lookup_keys_do_not_resolve(self):
        Skill.objects.filter(pk=self.skill.pk).update(name="Reading understanding")
        bad_lookups = (
            ({"name": self.skill.name}, {"version": 1, "source": "mcp"}),
            ({"name": self.skill.name, "category_id": self.category.pk, "extra": True}, {"version": 1, "source": "mcp"}),
            ({"name": self.skill.name, "category_id": self.category.pk}, {"version": 2, "source": "mcp"}),
            ({"name": self.skill.name, "category_id": self.category.pk}, {"version": 1, "source": "mcp", "extra": True}),
            ({"name": self.skill.name, "category_id": self.category.pk}, {"version": True, "source": "mcp"}),
        )
        for lookup, provenance in bad_lookups:
            with self.subTest(lookup=lookup, provenance=provenance):
                RPGContentOverride.objects.all().delete()
                self.retain(self.skill, lookup, provenance=provenance)
                self.assertIsNone(self.assert_native_identity(snapshot_catalog()))

    def test_incomplete_category_lookup_and_wrong_model_labels_are_ignored(self):
        SkillCategory.objects.filter(pk=self.category.pk).update(name="Language practice")
        for lookup in ({}, {"name": "Language Arts", "icon": ""}, {"name": ["Language Arts"]}):
            with self.subTest(lookup=lookup):
                RPGContentOverride.objects.all().delete()
                self.retain(self.category, lookup)
                self.assertIsNone(self.assert_native_identity(snapshot_catalog()))
        RPGContentOverride.objects.all().delete()
        RPGContentOverride.objects.create(
            model_label="achievements.subject", object_id=self.category.pk,
            source_lookup={"name": "Language Arts"}, values={"_authoring": {"version": 1, "source": "mcp"}},
        )
        self.assertIsNone(self.assert_native_identity(snapshot_catalog()))

    def test_deleted_retained_object_cannot_create_an_identity(self):
        self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
        self.skill.delete()
        self.assertIsNone(self.assert_native_identity(snapshot_catalog()))

    def test_retained_source_change_invalidates_identity_even_without_model_changes(self):
        Skill.objects.filter(pk=self.skill.pk).update(name="Reading understanding")
        before = snapshot_catalog()
        self.assertIsNone(self.assert_native_identity(before))
        override = self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
        after = snapshot_catalog()
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        self.assertIsNone(before.source_skills.get((self.category.pk, self.skill.name)))
        self.assertEqual(self.assert_native_identity(after), self.skill.pk)
        override.values["description"] = "Only unrelated authoring text changed"
        override.save(update_fields=["values"])
        self.assertEqual(after.fingerprint, snapshot_catalog().fingerprint)

    def test_snapshot_identity_maps_are_detached_and_immutable_after_rollback(self):
        with transaction.atomic():
            self.retain(self.category, {"name": self.category.name})
            self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
            SkillCategory.objects.filter(pk=self.category.pk).update(name="Preview language")
            Skill.objects.filter(pk=self.skill.pk).update(name="Preview Reading", category=self.other)
            catalog = snapshot_catalog()
            transaction.set_rollback(True)
        self.assertEqual(SkillCategory.objects.get(pk=self.category.pk).name, "Language Arts")
        with self.assertNumQueries(0):
            self.assertEqual(catalog.source_categories["Language Arts"], self.category.pk)
            self.assertEqual(catalog.source_skills[(self.category.pk, self.skill.name)], self.skill.pk)
        with self.assertRaises(TypeError):
            catalog.source_categories["Language Arts"] = 9000
        with self.assertRaises(TypeError):
            catalog.source_skills[(self.category.pk, self.skill.name)] = 9000
        with self.assertRaises(FrozenInstanceError):
            catalog.source_categories = {}

    def test_identity_reads_are_batched_and_load_no_private_authoring_fields(self):
        self.retain(self.category, {"name": self.category.name})
        self.retain(self.skill, {"name": self.skill.name, "category_id": self.category.pk})
        with CaptureQueriesContext(connection) as queries:
            catalog = snapshot_catalog()
        metadata_queries = [query["sql"] for query in queries if '"rpg_rpgcontentoverride"' in query["sql"].lower()]
        self.assertEqual(len(metadata_queries), 1)
        projection = metadata_queries[0].lower().split(" from ", 1)[0]
        self.assertNotIn('"family_id"', projection)
        self.assertNotIn('"values"', projection)
        self.assertNotIn('"publication_id"', projection)
        self.assertEqual(catalog.source_categories[self.category.name], self.category.pk)

    def test_legacy_catalog_constructor_has_safe_empty_identity_defaults(self):
        catalog = Catalog({}, {}, {}, {}, [], [], {}, "synthetic")
        self.assertEqual(dict(catalog.source_categories), {})
        self.assertEqual(dict(catalog.source_skills), {})
