"""Installed reward identities use exact provenance and reject ambiguous rows."""
from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory
from apps.achievements.source_identity import resolve_fixed_skill, resolve_source_identity
from apps.rpg.models import RPGContentOverride


class FixedSkillSourceIdentityTests(TestCase):
    def setUp(self):
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(name="Vocabulary", category=self.category)
        self.other_category = SkillCategory.objects.create(name="Other practice")

    def retain(self, obj, lookup, *, provenance=None):
        return RPGContentOverride.objects.create(
            model_label=obj._meta.label_lower, object_id=obj.pk,
            source_lookup=lookup,
            values={"_authoring": provenance if provenance is not None else {"version": 1, "source": "mcp"}},
        )

    def lookup(self):
        return {"name": "Vocabulary", "category_id": self.category.pk}

    def test_current_canonical_rows_without_source_metadata_remain_usable(self):
        self.assertEqual(resolve_fixed_skill("Language Arts", "Vocabulary"), self.skill)
        self.assertFalse(RPGContentOverride.objects.exists())

    def test_retained_category_and_reparented_skill_keep_original_identity(self):
        self.retain(self.category, {"name": "Language Arts"})
        self.retain(self.skill, self.lookup())
        self.category.name = "Communication"
        self.category.save(update_fields=["name"])
        self.skill.name = "Word practice"
        self.skill.category = self.other_category
        self.skill.save(update_fields=["name", "category"])
        self.assertEqual(resolve_fixed_skill("Language Arts", "Vocabulary"), self.skill)

    def test_current_and_retained_match_to_same_row_is_not_ambiguous(self):
        self.retain(self.category, {"name": "Language Arts"})
        self.retain(self.skill, self.lookup())
        self.assertEqual(resolve_fixed_skill("Language Arts", "Vocabulary"), self.skill)

    def test_retired_installed_rows_remain_destinations(self):
        self.category.is_retired = True
        self.category.save(update_fields=["is_retired"])
        self.skill.is_retired = True
        self.skill.save(update_fields=["is_retired"])
        self.assertEqual(resolve_fixed_skill("Language Arts", "Vocabulary"), self.skill)

    def test_missing_category_does_not_select_other_category_same_name_skill(self):
        self.skill.category = self.other_category
        self.skill.save(update_fields=["category"])
        self.category.delete()
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_missing_skill_does_not_select_other_category_same_name_skill(self):
        self.skill.category = self.other_category
        self.skill.save(update_fields=["category"])
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_competing_current_and_retained_category_fails_closed(self):
        self.retain(self.category, {"name": "Language Arts"})
        self.category.name = "Communication"
        self.category.save(update_fields=["name"])
        SkillCategory.objects.create(name="Language Arts")
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_competing_current_and_retained_skill_fails_closed(self):
        other = Skill.objects.create(name="Other words", category=self.other_category)
        self.retain(other, self.lookup())
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_two_distinct_retained_skills_without_current_match_fail_closed(self):
        self.retain(self.skill, self.lookup())
        self.skill.name = "Word practice"
        self.skill.save(update_fields=["name"])
        other = Skill.objects.create(name="Other words", category=self.other_category)
        self.retain(other, self.lookup())
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_dangling_retained_ids_neither_create_a_destination_nor_a_tie(self):
        row = self.retain(self.skill, self.lookup())
        row.object_id = self.skill.pk + 10000
        row.save(update_fields=["object_id"])
        self.assertEqual(resolve_fixed_skill("Language Arts", "Vocabulary"), self.skill)
        self.skill.delete()
        self.assertIsNone(resolve_fixed_skill("Language Arts", "Vocabulary"))

    def test_retained_source_requires_exact_versioned_authoring_provenance(self):
        row = self.retain(self.skill, self.lookup())
        self.skill.name = "Word practice"
        self.skill.save(update_fields=["name"])
        for provenance in (
            {}, {"version": 2, "source": "mcp"}, {"version": 1, "source": "other"},
            {"version": 1, "source": "mcp", "unrecognized": True},
        ):
            with self.subTest(provenance=provenance):
                row.values = {"_authoring": provenance}
                row.save(update_fields=["values"])
                self.assertIsNone(resolve_source_identity(Skill, self.lookup()))

    def test_retained_source_requires_exact_complete_lookup(self):
        row = self.retain(self.skill, self.lookup())
        self.skill.name = "Word practice"
        self.skill.save(update_fields=["name"])
        for lookup in (
            {"name": "Vocabulary"},
            {"name": "Vocabulary", "category_id": self.other_category.pk},
            {**self.lookup(), "unrecognized": True},
        ):
            with self.subTest(lookup=lookup):
                row.source_lookup = lookup
                row.save(update_fields=["source_lookup"])
                self.assertIsNone(resolve_source_identity(Skill, self.lookup()))
