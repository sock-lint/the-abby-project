"""Real-load deferrals retain one named cause across bundled-pack boundaries."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, RetiredContentReference
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupLiveDeferralWarningTests(TestCase):
    @staticmethod
    def quest(name, **values):
        if values.get("prerequisite_quest"):
            values["trigger_filter"] = {"allowed_triggers": ["reading_logged"]}
        return {"name": name, "quest_type": "collection", "target_value": 2, **values}

    @staticmethod
    def badge(name, quest_name):
        return {"name": name, "criteria_type": "quest_completed",
                "criteria_value": {"quest_name": quest_name}, "xp_bonus": 0, "award_coins": False}

    def run_sources(self, sources):
        with TemporaryDirectory() as directory:
            paths = []
            for index, source in enumerate(sources):
                path = Path(directory) / f"warnings-pack-{index}"
                path.mkdir()
                paths.append((str(path), ""))
                for section, data in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(data))
            output = StringIO()
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple(paths)), patch(
                    "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                call_command("loadrpgcontent", stdout=output)
            return output.getvalue()

    def chain_sources(self, root, *, release):
        return [
            {"skill_tree": {"categories": [{"name": "Runtime"}], "skills": [
                {"name": "Old", "category": "Runtime"}, {"name": "New", "category": "Runtime"}]},
             "quests": {"quests": [self.quest("Seed", skill_tags=["Runtime::Old"])] +
                        ([root] if release else [])}},
            {"badges": {"badges": [self.badge("Root complete", root["name"])] if release else []},
             "quests": {"quests": [self.quest("After root", prerequisite_quest=root["name"]),
                self.quest("Gated root", required_badge="Root complete")] if release else []}},
            {"badges": {"badges": [self.badge("Gate complete", "Gated root")] if release else []},
             "quests": {"quests": [self.quest("Later gate", required_badge="Gate complete")] if release else []}},
        ]

    def warning_causes(self, output, names):
        warnings = [line.strip() for line in output.splitlines() if "warning:" in line]
        return {name: next(line.split(" unchanged: ", 1)[1] for line in warnings
                          if f" {name!r} unchanged: " in line) for name in names}

    def test_actual_retirement_deferral_keeps_one_named_root_through_later_packs(self):
        root = self.quest("Runtime root", skill_tags=["Runtime::New"])
        self.run_sources(self.chain_sources(root, release=False))
        Skill.objects.filter(name="New", category__name="Runtime").update(is_retired=True)

        output = self.run_sources(self.chain_sources(root, release=True))

        dependents = ["Root complete", "After root", "Gated root", "Gate complete", "Later gate"]
        causes = self.warning_causes(output, [root["name"], *dependents])
        # The generic admission failure arises only during the real row write:
        # preflight can still resolve the existing, retired skill's identity.
        self.assertIn("Retired taxonomy entries", causes[root["name"]])
        expected = f"Quest source {root['name']!r} was deferred: {causes[root['name']]}"
        for name in dependents:
            with self.subTest(name=name):
                self.assertEqual(causes[name], expected)
                self.assertEqual(causes[name].count(" source "), 1)
        self.assertEqual(set(QuestDefinition.objects.values_list("name", flat=True)), {"Seed"})
        self.assertFalse(Badge.objects.exists())
        self.assertTrue(Skill.objects.get(name="New", category__name="Runtime").is_retired)

    def test_planned_skill_and_category_causes_pass_through_without_extra_prefixes(self):
        actor = make_family(parents=[{"username": "warning-parent", "is_staff": True}]).parents[0]
        renamed = SkillCategory.objects.create(name="Retained route")
        RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=renamed.pk,
            family=actor.family, source_lookup={"name": "source route"},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        SkillCategory.objects.create(name="Archived route", is_retired=True)
        output = self.run_sources([
            {"skill_tree": {"categories": [{"name": "Source route"}, {"name": "Archived route"}],
                "skills": [{"name": "Fresh", "category": "Archived route"}]},
             "quests": {"quests": [self.quest("Planned root", skill_tags=["Archived route::Fresh"])]},
             "badges": {"badges": [{"name": "Source mastery", "criteria_type": "category_mastery",
                "criteria_value": {"category": "Source route", "min_level": 1},
                "xp_bonus": 0, "award_coins": False}]}},
            {"badges": {"badges": [self.badge("Planned complete", "Planned root")]},
             "quests": {"quests": [self.quest("Planned after", prerequisite_quest="Planned root"),
                self.quest("Planned gate", required_badge="Planned complete"),
                self.quest("Mastery gate", required_badge="Source mastery")]}},
            {"quests": {"quests": [self.quest("Planned root", skill_tags=["Archived route::Fresh"])]},
             "badges": {"badges": [{"name": "Source mastery", "criteria_type": "category_mastery",
                "criteria_value": {"category": "Source route", "min_level": 1},
                "xp_bonus": 0, "award_coins": False}]}},
        ])
        causes = self.warning_causes(output, ["Planned root", "Planned complete", "Planned after",
                                             "Planned gate", "Source mastery", "Mastery gate"])
        skill_reason = "Skill source 'Archived route::Fresh' was deferred for a retired reference."
        category_reason = "Category source 'Source route' was deferred for a retained category identity conflict."
        for name, cause in causes.items():
            with self.subTest(name=name):
                self.assertEqual(cause, category_reason if name in {"Source mastery", "Mastery gate"} else skill_reason)
        # Multiple bundles may revisit the same global source. Its later
        # warning must retain the original named cause without wrapping it.
        for name, expected in (("Planned root", skill_reason), ("Source mastery", category_reason)):
            repeated = [line.split(" unchanged: ", 1)[1] for line in output.splitlines()
                        if "warning:" in line and f" {name!r} unchanged: " in line]
            self.assertEqual(repeated, [expected, expected])
        self.assertFalse(QuestDefinition.objects.exists())
        self.assertFalse(Badge.objects.exists())

    def test_manual_load_keeps_the_original_retirement_exception(self):
        category = SkillCategory.objects.create(name="Manual")
        Skill.objects.create(name="Retired", category=category, is_retired=True)
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "quests.yaml").write_text(yaml.safe_dump({"quests": [
                self.quest("Manual root", skill_tags=["Manual::Retired"])]}))
            with self.assertRaises(RetiredContentReference) as caught:
                ContentPack(path).load()
        self.assertTrue(str(caught.exception).startswith("Retired taxonomy entries"))
        self.assertFalse(QuestDefinition.objects.exists())
