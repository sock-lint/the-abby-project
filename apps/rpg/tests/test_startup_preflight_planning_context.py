"""Dependency-planning failures identify the source bundle before any load."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, StartupDeferrals
from apps.rpg.models import ContentPackEntry, ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupPreflightPlanningContextTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "planning-parent", "is_staff": True}]).parents[0]

    def retain_source(self, model, name, lookup):
        row = model.objects.create(name=name)
        RPGContentOverride.objects.create(model_label=model._meta.label_lower, object_id=row.pk,
            family=self.actor.family, source_lookup=lookup,
            values={"_authoring": {"version": 1, "source": "mcp"}})
        return row

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values())
                for model in (SkillCategory, Skill, Badge, QuestDefinition, ItemDefinition,
                              ContentPackEntry, RPGContentOverride)}

    def assert_planning_failure(self, bad_source, message, *, with_retired_skill=True, bad_position):
        sources = [{"skill_tree": {"categories": [{"name": "A"}],
                       "skills": [{"name": "B::C", "category": "A"}]}} if with_retired_skill else {}
                   for _ in range(3)]
        sources[bad_position] = bad_source
        before = self.snapshot()
        with TemporaryDirectory() as directory:
            selections = []
            for index, source in enumerate(sources):
                path = Path(directory) / f"planning-pack-{index}"
                path.mkdir()
                selections.append((str(path), ""))
                for section, value in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            for dry_run in (False, True):
                with self.subTest(dry_run=dry_run):
                    output = StringIO()
                    state = StartupDeferrals()
                    with patch("apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state), patch(
                            "apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple(selections)), patch(
                            "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None), patch.object(
                            ContentPack, "load", side_effect=AssertionError("Planning must fail before any actual pack load")) as load:
                        with self.assertRaises(CommandError) as raised:
                            call_command("loadrpgcontent", dry_run=dry_run, stdout=output)
                    load.assert_not_called()
                    self.assertEqual(self.snapshot(), before)
                    self.assertNotIn("Loading pack:", output.getvalue())
                    self.assertIn(message, str(raised.exception))
                    self.assertIn(selections[bad_position][0], str(raised.exception))
                    for index, selection in enumerate(selections):
                        if index != bad_position:
                            self.assertNotIn(selection[0], str(raised.exception))
                    self.assertEqual(state.source_paths, {})

    def test_quest_planning_ambiguity_names_its_source_at_every_position(self):
        SkillCategory.objects.create(name="A", is_retired=True)
        # A legacy current name and another row's retained source can tie.
        # The whole qualified spelling can also describe A / B::C, so the
        # retired-skill planner must try both boundaries and reject the tie.
        SkillCategory.objects.create(name="A::B")
        self.retain_source(SkillCategory, "Renamed A::B", {"name": "A::B"})
        for bad_position in range(3):
            with self.subTest(bad_position=bad_position):
                self.assert_planning_failure({"quests": {"quests": [{
                    "name": "Later ambiguous challenge", "quest_type": "collection", "target_value": 2,
                    "skill_tags": ["A::B::C"]}]}}, "unknown or ambiguous skill category source 'A::B'", bad_position=bad_position)

    def test_badge_planning_identity_error_names_its_source_at_every_position(self):
        SkillCategory.objects.create(name="A", is_retired=True)
        for name in ("First saved badge", "Second saved badge"):
            self.retain_source(Badge, name, {"name": "Shared badge"})
        for bad_position in range(3):
            with self.subTest(bad_position=bad_position):
                self.assert_planning_failure({"badges": {"badges": [{
                    "name": "Shared badge", "criteria_type": "projects_completed", "criteria_value": {"count": 1},
                    "xp_bonus": 0, "award_coins": False}]}}, "More than one authored entry retains this exact source identity", bad_position=bad_position)

    def test_category_source_check_names_its_loader_at_every_position(self):
        for name in ("First saved route", "Second saved route"):
            self.retain_source(SkillCategory, name, {"name": "Shared route"})
        for bad_position in range(3):
            with self.subTest(bad_position=bad_position):
                self.assert_planning_failure({"skill_tree": {"categories": [{"name": "Shared route"}]}},
                    "More than one authored entry retains this exact source identity", with_retired_skill=False, bad_position=bad_position)
