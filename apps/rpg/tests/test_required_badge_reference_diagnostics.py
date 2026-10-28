"""Native required-badge diagnostics retain legacy lookup coercion."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import CommandError, call_command
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import ContentPackEntry, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RequiredBadgeReferenceDiagnosticsTests(TestCase):
    modes = (("default", False, False), ("default", True, False),
             ("default", False, True), ("default", True, True),
             ("manual", False, False), ("manual", True, False),
             ("keyed", False, False), ("keyed", True, False))

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values())
                for model in (SkillCategory, Skill, Badge, QuestDefinition, ContentPackEntry, RPGContentOverride)}

    def assert_workflow(self, reference, mode, dry_run, seed, *, installed=False, retained_alias=False):
        with transaction.atomic():
            badge = None
            if retained_alias:
                family = make_family(parents=[{"username": "required-badge-parent", "is_staff": True}]).family
                badge = Badge.objects.create(name="Renamed numeric badge", criteria_type="projects_completed", criteria_value={"count": 1})
                RPGContentOverride.objects.create(model_label="achievements.badge", object_id=badge.pk,
                    family=family, source_lookup={"name": "5"}, values={"_authoring": {"version": 1, "source": "mcp"}})
            elif installed and reference is not None:
                badge = Badge.objects.create(name=str(reference), criteria_type="projects_completed", criteria_value={"count": 1})
            source = {"quests": {"quests": [
                {"id": "prefix", "name": "Before reference", "description": "Rollback control", "quest_type": "collection", "target_value": 1},
                {"id": "odd", "name": "Odd", "description": "Reference control", "quest_type": "collection", "target_value": 1, "required_badge": reference}]}}
            if seed:
                SkillCategory.objects.create(name="Archive", is_retired=True)
                source["skill_tree"] = {"categories": [{"name": "Archive"}], "skills": [{"name": "Fresh", "category": "Archive"}]}
                source["quests"]["quests"].append({"name": "Missing", "description": "Retired dependency", "quest_type": "collection", "target_value": 1, "skill_tags": ["Archive::Fresh"]})
            before = self.snapshot()
            should_resolve = reference is None or (isinstance(reference, str) if retained_alias else installed)
            error = None
            try:
                with TemporaryDirectory() as directory:
                    path = Path(directory)
                    for section, entries in source.items():
                        (path / f"{section}.yaml").write_text(yaml.safe_dump(entries))
                    try:
                        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", ((str(path), ""),)), patch(
                                "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                            if mode == "keyed":
                                ContentPack(path, pack_key="required-badge-control").load(stdout=StringIO(), dry_run=dry_run)
                            else:
                                options = {"pack": str(path)} if mode == "manual" else {}
                                call_command("loadrpgcontent", stdout=StringIO(), dry_run=dry_run, **options)
                    except Exception as exc:
                        error = exc
                if should_resolve:
                    self.assertIsNone(error, f"Native lookup must remain accepted: {error!r}")
                    if not dry_run:
                        quest = QuestDefinition.objects.get(name="Odd")
                        self.assertEqual(quest.required_badge_id, badge.pk if badge and reference is not None else None)
                        self.assertTrue(QuestDefinition.objects.filter(name="Before reference").exists())
                else:
                    expected = ContentPackError if mode == "keyed" else CommandError
                    self.assertIsInstance(error, expected, f"Native reference failure must remain a normal diagnostic: {error!r}")
                    self.assertIn("unknown badge or ambiguous source", str(error))
                    self.assertIn(repr(reference), str(error))
                if dry_run or not should_resolve:
                    self.assertEqual(self.snapshot(), before)
            finally:
                transaction.set_rollback(True)

    def test_unknown_unhashable_references_keep_native_diagnostics_and_rollback(self):
        for reference in (["X"], {"x": 1}, [], {}):
            for mode, dry, seed in self.modes:
                with self.subTest(reference=reference, mode=mode, dry=dry, seed=seed):
                    self.assert_workflow(reference, mode, dry, seed)

    def test_existing_textual_names_keep_native_unhashable_reference_coercion(self):
        for reference in (["X"], {"x": 1}, [], {}):
            for mode, dry, seed in self.modes:
                with self.subTest(reference=reference, mode=mode, dry=dry, seed=seed):
                    self.assert_workflow(reference, mode, dry, seed, installed=True)

    def test_hashable_numeric_text_and_null_controls_keep_native_semantics(self):
        for reference in (5, 2.5, True, 0, False, "", "Ordinary", None):
            for installed in (False, True):
                for mode, dry, seed in self.modes:
                    with self.subTest(reference=reference, installed=installed, mode=mode, dry=dry, seed=seed):
                        self.assert_workflow(reference, mode, dry, seed, installed=installed)

    def test_numeric_lookup_is_not_rewritten_into_a_retained_text_alias(self):
        for reference in (5, "5"):
            for mode, dry, seed in self.modes:
                with self.subTest(reference=reference, mode=mode, dry=dry, seed=seed):
                    self.assert_workflow(reference, mode, dry, seed, retained_alias=True)
