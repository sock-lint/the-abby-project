"""Selective startup planning preserves non-strict legacy badge loading."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.models import ContentPackEntry, ItemDefinition


class StartupLegacyBadgePlanningTests(TestCase):
    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values(
                    *(field.attname for field in model._meta.concrete_fields if not getattr(field, "auto_now", False))))
                for model in (SkillCategory, Skill, Badge, QuestDefinition, ItemDefinition, ContentPackEntry)}

    def assert_legacy_load(self, rule, *, criteria_type="quest_completed", retired=True, expected_badge=True):
        if retired:
            SkillCategory.objects.create(name="Legacy route", is_retired=True)
        source = {"skill_tree": {"categories": [{"name": "Legacy route"}],
                  "skills": [{"name": "Legacy skill", "category": "Legacy route"}]},
                  "quests": {"quests": [
                      {"name": "Tagged", "quest_type": "collection", "target_value": 1,
                       "skill_tags": ["Legacy route::Legacy skill"]},
                      {"name": "Other", "quest_type": "collection", "target_value": 1}]}}
        badge = {"badges": {"badges": [{"name": "Legacy badge", "criteria_type": criteria_type,
                  "criteria_value": rule, "xp_bonus": 0, "award_coins": False}]}}
        marker = {"items": {"items": [{"name": "Unaffected marker", "slug": "legacy-badge-marker", "item_type": "food"}]}}
        before = self.snapshot()
        with TemporaryDirectory() as directory:
            selections = []
            for index, pack in enumerate((source, marker, badge)):
                path = Path(directory) / str(index)
                path.mkdir()
                selections.append((str(path), ""))
                for section, value in pack.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple(selections)), patch(
                    "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                output = StringIO()
                try:
                    call_command("loadrpgcontent", dry_run=True, stdout=output)
                except Exception as exc:
                    self.fail(f"Legacy default startup must remain loadable: {type(exc).__name__}: {exc}")
                self.assertEqual(self.snapshot(), before)
                previous = None
                for _ in range(2):
                    output = StringIO()
                    call_command("loadrpgcontent", stdout=output)
                    self.assertEqual(output.getvalue().count("Loading pack:"), 3)
                    self.assertTrue(ItemDefinition.objects.filter(slug="legacy-badge-marker").exists())
                    self.assertTrue(QuestDefinition.objects.filter(name="Other").exists())
                    self.assertEqual(Badge.objects.filter(name="Legacy badge").exists(), expected_badge)
                    if expected_badge:
                        self.assertEqual(Badge.objects.get(name="Legacy badge").criteria_value, rule)
                    after = self.snapshot()
                    if previous is not None:
                        self.assertEqual(after, previous)
                    previous = after

    def test_nonobject_project_criteria_survive_with_retired_source(self):
        self.assert_legacy_load("one", criteria_type="projects_completed")

    def test_nonobject_project_criteria_survive_without_deferrals(self):
        self.assert_legacy_load([1], criteria_type="projects_completed", retired=False)

    def test_nonobject_quest_criteria_survive_with_retired_source(self):
        self.assert_legacy_load("one")

    def test_uncoercible_completion_count_survives_with_deferred_named_quest(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"], "count": "three"})

    def test_non_scalar_completion_count_survives_with_deferred_named_quest(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"], "count": [2]})

    def test_uncoercible_completion_count_without_deferral_stays_unchanged(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"], "count": "three"}, retired=False)

    def test_valid_completion_count_still_defers_unreachable_badge(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"], "count": 2}, expected_badge=False)

    def test_legacy_numeric_text_count_uses_native_integer_coercion(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"], "count": "2"}, expected_badge=False)

    def test_native_any_of_completion_still_uses_surviving_alternative(self):
        self.assert_legacy_load({"quest_names": ["Tagged", "Other"]})

    def test_noniterable_completion_names_preserve_legacy_startup(self):
        self.assert_legacy_load({"quest_names": 7, "count": 1})

    def test_unhashable_completion_names_preserve_legacy_startup(self):
        self.assert_legacy_load({"quest_names": ["Tagged", ["Other"]], "count": 2})

    def test_unhashable_singular_completion_name_preserves_legacy_startup(self):
        self.assert_legacy_load({"quest_name": ["Tagged"]})
