"""Catch YAML/catalog drift before it lands in production.

The ``loadrpgcontent`` command is upsert-only — it can't remove rows that
were once seeded but later removed from the YAML. The
``cleanup_rpg_catalog`` command exists to delete those, but only knows
about the names listed in ``LEGACY_*`` / ``DUPLICATE_*`` / ``RETIRED_*``
constants. Without a check, an author can drop a badge from
``badges.yaml`` and the production DB silently keeps the orphan forever.

This test reloads RPG content into a fresh DB, then asserts that every
catalog row in the loadable categories (badges, quest definitions, skill
categories) is either represented in the YAML OR explicitly listed in
the cleanup constants. A failure means: either re-add it to YAML, or add
it to the matching cleanup constant.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Badge, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.management.commands.cleanup_rpg_catalog import (
    DUPLICATE_BADGES,
    LEGACY_SKILL_CATEGORIES,
    RETIRED_QUESTS,
)
from apps.rpg.management.commands.loadrpgcontent import BUNDLED_PACKS


REPO_ROOT = Path(__file__).resolve().parents[3]


def _yaml_names(filename: str, top_key: str, name_key: str = "name") -> set[str]:
    names = set()
    for pack_path, _namespace in BUNDLED_PACKS:
        path = REPO_ROOT / pack_path / filename
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text()) or {}
        names.update(entry[name_key] for entry in (data.get(top_key) or []) if entry.get(name_key))
    return names


class CatalogDriftTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Idempotent — load the production YAML into the test DB exactly
        # the way deploy does. Don't run cleanup_rpg_catalog here — the
        # whole point of this test is to surface drift the cleanup would
        # need to know about but doesn't yet.
        call_command("loadrpgcontent")

    def test_no_orphan_badges(self):
        """Every Badge row must be in a bundled pack or DUPLICATE_BADGES."""
        in_yaml = _yaml_names("badges.yaml", "badges")
        allow = in_yaml | set(DUPLICATE_BADGES)
        rows = set(Badge.objects.values_list("name", flat=True))
        orphans = sorted(rows - allow)
        if orphans:
            self.fail(
                "Badge rows not present in badges.yaml AND not in "
                "DUPLICATE_BADGES (apps/rpg/management/commands/"
                "cleanup_rpg_catalog.py): "
                f"{orphans}. Re-add to YAML OR add to DUPLICATE_BADGES "
                "with a comment explaining the retirement.",
            )

    def test_no_orphan_quests(self):
        in_yaml = _yaml_names("quests.yaml", "quests")
        allow = in_yaml | set(RETIRED_QUESTS)
        # Smoke-test rows are stripped on every run, never authored — exclude.
        rows = set(
            QuestDefinition.objects
            .exclude(name__startswith="MCP-SmokeTest-")
            .values_list("name", flat=True),
        )
        orphans = sorted(rows - allow)
        if orphans:
            self.fail(
                "QuestDefinition rows not present in quests.yaml AND not "
                "in RETIRED_QUESTS: "
                f"{orphans}. Re-add to YAML OR add to RETIRED_QUESTS.",
            )

    def test_no_orphan_skill_categories(self):
        in_yaml = _yaml_names("skill_tree.yaml", "categories")
        allow = in_yaml | set(LEGACY_SKILL_CATEGORIES)
        rows = set(SkillCategory.objects.values_list("name", flat=True))
        orphans = sorted(rows - allow)
        if orphans:
            self.fail(
                "SkillCategory rows not present in skill_tree.yaml AND not "
                "in LEGACY_SKILL_CATEGORIES: "
                f"{orphans}. Re-add to YAML OR add to LEGACY_SKILL_CATEGORIES.",
            )

    def test_unregistered_catalog_rows_still_fail_the_drift_guards(self):
        cases = (
            (Badge, {"criteria_type": "first_project"}, self.test_no_orphan_badges),
            (QuestDefinition, {"quest_type": "collection", "target_value": 1}, self.test_no_orphan_quests),
            (SkillCategory, {}, self.test_no_orphan_skill_categories),
        )
        for model, fields, check in cases:
            with self.subTest(model=model.__name__):
                orphan = model.objects.create(name="Unregistered catalog drift", **fields)
                with self.assertRaisesRegex(AssertionError, "Unregistered catalog drift"):
                    check()
                orphan.delete()
                check()
