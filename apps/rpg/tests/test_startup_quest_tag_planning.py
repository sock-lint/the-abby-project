"""Malformed quest tag names retain the native startup error and pack origin."""
from contextlib import contextmanager
from dataclasses import fields
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition, QuestSkillTag
from apps.rpg.content.loader import StartupDeferrals
from apps.rpg.models import ItemDefinition, RPGContentRetirement
from apps.rpg.retired_catalog import RETIREMENT_KEY


class StartupQuestTagPlanningTests(TestCase):
    message = "Quest skill references must be nonempty names."

    def setUp(self):
        RPGContentRetirement.objects.update_or_create(key=RETIREMENT_KEY, defaults={"applied_at": timezone.now()})

    def snapshot(self):
        return {model: list(model.objects.order_by("pk").values())
            for model in (SkillCategory, Skill, QuestDefinition, QuestSkillTag, Badge, ItemDefinition)}

    @staticmethod
    def quest(name, tags):
        return {"name": name, "quest_type": "collection", "target_value": 1, "skill_tags": tags}

    @contextmanager
    def packs(self, sources):
        with TemporaryDirectory() as directory:
            paths = []
            for index, source in enumerate(sources):
                path = Path(directory) / f"quest-tags-pack-{index}"
                path.mkdir()
                paths.append(path)
                for section, value in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS",
                       tuple((str(path), "") for path in paths)):
                yield paths

    def failure(self, sources, bad_pack, *, dry_run=False, explicit=False, contextual=True):
        before, state, output = self.snapshot(), StartupDeferrals(), StringIO()
        with self.packs(sources) as paths, patch(
                "apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state):
            error = None
            try:
                call_command("loadrpgcontent", stdout=output, dry_run=dry_run,
                    **({"pack": str(paths[bad_pack])} if explicit else {}))
            except Exception as exc:  # Classify failures so a raw error is a behavioral assertion failure.
                error = exc
            self.assertIsInstance(error, CommandError)
            self.assertIn(self.message, str(error))
            if contextual:
                self.assertIn(str(paths[bad_pack]), str(error))
                for index, path in enumerate(paths):
                    if index != bad_pack:
                        self.assertNotIn(str(path), str(error))
                self.assertNotIn("Loading pack:", output.getvalue())
            else:
                self.assertEqual(str(error), self.message)
                self.assertIn("Loading pack: " + str(paths[bad_pack]), output.getvalue())
            self.assertEqual(self.snapshot(), before)
            self.assertTrue(all(not getattr(state, field.name) for field in fields(state)))

    def test_nontext_tag_names_keep_the_native_error_and_exact_pack_context(self):
        SkillCategory.objects.create(name="Tag archive", is_retired=True)
        for value in (5, ["Arts::Paint"], None, True, {"x": 1}, 5.5):
            for dry_run in (False, True):
                with self.subTest(value=value, dry_run=dry_run):
                    self.failure([
                        {"skill_tree": {"categories": [{"name": "Tag archive"}],
                            "skills": [{"name": "Fresh", "category": "Tag archive"}]}},
                        {"quests": {"quests": [self.quest("Invalid tag", [{"skill": value}])]}}
                    ], 1, dry_run=dry_run)

    def test_context_follows_same_pack_source_retirement_and_later_pack(self):
        for kind in ("same", "source-retirement", "third"):
            for dry_run in (False, True):
                with self.subTest(kind=kind, dry_run=dry_run):
                    category = SkillCategory.objects.create(name=f"Context archive {kind} {dry_run}",
                        is_retired=kind != "source-retirement")
                    tree = {"categories": [{"name": category.name,
                        **({"is_retired": True} if kind == "source-retirement" else {})}],
                        "skills": [{"name": "Fresh", "category": category.name}]}
                    bad = {"quests": {"quests": [self.quest("Invalid tag", [{"skill": ["Arts::Paint"]}])]}}
                    sources = [{"skill_tree": tree, **bad}] if kind == "same" else [{"skill_tree": tree}]
                    if kind == "third":
                        sources.append({"items": {"items": [{"name": "Rollback marker", "slug": "tag-rollback-marker", "item_type": "food"}]}})
                    if kind != "same":
                        sources.append(bad)
                    self.failure(sources, len(sources) - 1, dry_run=dry_run)

    def test_native_no_deferral_and_explicit_failure_paths_remain_unchanged(self):
        for explicit in (False, True):
            for dry_run in (False, True):
                with self.subTest(explicit=explicit, dry_run=dry_run):
                    self.failure([
                        {"quests": {"quests": [self.quest("Invalid tag", [{"skill": 5}])]}}
                    ], 0, dry_run=dry_run, explicit=explicit, contextual=False)

    def test_valid_text_and_weighted_names_load_and_reload_beside_an_unrelated_refusal(self):
        SkillCategory.objects.create(name="Positive archive", is_retired=True)
        sources = [
            {"skill_tree": {"categories": [{"name": "Positive archive"}, {"name": "Arts"}],
                "skills": [{"name": "Fresh", "category": "Positive archive"}, {"name": "Paint", "category": "Arts"}]}},
            {"quests": {"quests": [self.quest("Text tag", ["Arts::Paint"]),
                self.quest("Weighted tag", [{"skill": "Arts::Paint", "weight": 2}])]}}
        ]
        before = self.snapshot()
        with self.packs(sources):
            call_command("loadrpgcontent", stdout=StringIO(), dry_run=True)
        self.assertEqual(self.snapshot(), before)
        for _reload in range(2):
            with self.packs(sources):
                call_command("loadrpgcontent", stdout=StringIO())
            self.assertFalse(Skill.objects.filter(name="Fresh").exists())
            self.assertEqual(QuestSkillTag.objects.get(quest_definition__name="Text tag").xp_weight, 1)
            self.assertEqual(QuestSkillTag.objects.get(quest_definition__name="Weighted tag").xp_weight, 2)
