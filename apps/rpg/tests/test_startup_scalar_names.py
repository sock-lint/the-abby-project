"""Default startup retains the native legacy scalar-name contract."""
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupScalarNameTests(TestCase):
    tree = {"categories": [{"name": "Arch"}], "skills": [{"name": "Fresh", "category": "Arch"}]}

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values())
                for model in (SkillCategory, Skill, Badge, QuestDefinition, RPGContentOverride)}

    def load(self, source, dry_run):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            for section, data in source.items():
                (path / f"{section}.yaml").write_text(yaml.safe_dump(data))
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", ((str(path), ""),)), patch(
                    "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                call_command("loadrpgcontent", stdout=StringIO(), dry_run=dry_run)

    def source(self, kind, name):
        quests = [{"name": "P", "quest_type": "collection", "target_value": 2, "skill_tags": ["Arch::Fresh"]},
                  {"name": "Other", "quest_type": "collection", "target_value": 2}]
        badges = [{"name": "Plain", "criteria_type": "projects_completed", "criteria_value": {"count": 2}}]
        if kind == "quest":
            quests.append({"name": name, "quest_type": "collection", "target_value": 2})
        else:
            badges.append({"name": name, "criteria_type": "projects_completed", "criteria_value": {"count": 1}})
        return {"skill_tree": self.tree, "quests": {"quests": quests}, "badges": {"badges": badges}}

    def assert_scalar_workflow(self, kind, name):
        for retired in (False, True):
            for dry_run in (False, True):
                with self.subTest(kind=kind, name=name, retired=retired, dry_run=dry_run), transaction.atomic():
                    try:
                        if retired:
                            SkillCategory.objects.create(name="Arch", is_retired=True)
                        before = self.snapshot()
                        self.load(self.source(kind, name), dry_run)
                        if dry_run:
                            self.assertEqual(self.snapshot(), before)
                        else:
                            expected_quests = {"Other"} | (set() if retired else {"P"})
                            expected_badges = {"Plain"}
                            (expected_quests if kind == "quest" else expected_badges).add(str(name))
                            self.assertSetEqual(set(QuestDefinition.objects.values_list("name", flat=True)), expected_quests)
                            self.assertSetEqual(set(Badge.objects.values_list("name", flat=True)), expected_badges)
                            self.assertEqual(Skill.objects.filter(name="Fresh").exists(), not retired)
                    finally:
                        transaction.set_rollback(True)

    def test_integer_quest_name_loads_with_selective_retirement(self):
        self.assert_scalar_workflow("quest", 2048)

    def test_date_quest_name_loads_with_selective_retirement(self):
        self.assert_scalar_workflow("quest", date(2026, 5, 1))

    def test_integer_badge_name_loads_with_selective_retirement(self):
        self.assert_scalar_workflow("badge", 1000)

    def test_boolean_badge_name_loads_with_selective_retirement(self):
        self.assert_scalar_workflow("badge", True)

    def test_scalar_and_text_source_aliases_keep_distinct_identities(self):
        cases = (("quest", 2048, 2048), ("quest", 2048, "2048"),
                 ("quest", "2048", 2048), ("quest", "2048", "2048"),
                 ("quest", date(2026, 5, 1), "2026-05-01"),
                 ("badge", True, True), ("badge", True, "True"),
                 ("badge", "True", True), ("badge", "True", "True"))
        for kind, name, alias in cases:
            for dry_run in (False, True):
                with self.subTest(kind=kind, name=name, alias=alias, dry_run=dry_run), transaction.atomic():
                    try:
                        family = make_family(parents=[{"username": "scalar-name-parent", "is_staff": True}]).family
                        SkillCategory.objects.create(name="Arch", is_retired=True)
                        model = QuestDefinition if kind == "quest" else Badge
                        defaults = ({"quest_type": "collection", "target_value": 99, "is_system": True}
                                    if kind == "quest" else {"criteria_type": "projects_completed", "criteria_value": {"count": 99}})
                        saved = model.objects.create(name="Renamed source", **defaults)
                        RPGContentOverride.objects.create(model_label=model._meta.label_lower, object_id=saved.pk,
                            family=family, source_lookup={"name": alias}, values={"_authoring": {"version": 1, "source": "mcp"}})
                        before = self.snapshot()
                        self.load(self.source(kind, name), dry_run)
                        saved.refresh_from_db()
                        if dry_run:
                            self.assertEqual(self.snapshot(), before)
                        else:
                            self.assertEqual(model.objects.filter(name=str(name)).exists(), type(name) is not type(alias) or name != alias)
                            self.assertEqual(saved.target_value if kind == "quest" else saved.criteria_value["count"], 99)
                            self.assertFalse(QuestDefinition.objects.filter(name="P").exists())
                            self.assertTrue(QuestDefinition.objects.filter(name="Other").exists())
                    finally:
                        transaction.set_rollback(True)
