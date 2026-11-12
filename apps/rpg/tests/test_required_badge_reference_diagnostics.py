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
from apps.rpg.content.loader import ContentPack, ContentPackError, StartupDeferrals
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

    def startup_sources(self, sources, *, dry_run=False):
        out = StringIO()
        with TemporaryDirectory() as directory:
            paths = []
            for index, source in enumerate(sources):
                path = Path(directory) / f"pack-{index}"
                path.mkdir()
                paths.append((str(path), ""))
                for section, data in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple(paths)), patch(
                    "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                call_command("loadrpgcontent", stdout=out, dry_run=dry_run)
        return out.getvalue()

    def assert_withheld_coercion(self, reference, name):
        for reason in ("retired", "conflict"):
            for saved in (False, True):
                for split in (False, True):
                    for dry_run in (False, True):
                        with self.subTest(reference=reference, name=name, reason=reason, saved=saved,
                                          split=split, dry_run=dry_run), transaction.atomic():
                            try:
                                if reason == "retired":
                                    SkillCategory.objects.create(name="Archive", is_retired=True)
                                    category, skill = "Archive", "Fresh"
                                else:
                                    family = make_family(parents=[{"username": "coerced-badge-parent", "is_staff": True}]).family
                                    category_row = SkillCategory.objects.create(name="Renamed robotics")
                                    RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category_row.pk,
                                        family=family, source_lookup={"name": "robotics"},
                                        values={"_authoring": {"version": 1, "source": "mcp"}})
                                    category, skill = "Robotics", "Servo"
                                previous = Badge.objects.create(name=str(name), description="Saved badge", criteria_type="projects_completed",
                                    criteria_value={"count": 1}) if saved else None
                                tree = {"categories": [{"name": category}], "skills": [{"name": skill, "category": category}]}
                                root = {"name": "Root", "quest_type": "collection", "target_value": 1, "skill_tags": [f"{category}::{skill}"]}
                                badge = {"name": name, "description": "Source edit", "criteria_type": "quest_completed", "criteria_value": {"quest_names": ["Root"]}}
                                odd = {"name": "Odd", "quest_type": "collection", "target_value": 1, "required_badge": reference}
                                sources = [{"skill_tree": tree, "badges": {"badges": [badge]}, "quests": {"quests": [root]}}]
                                if split:
                                    sources.append({"quests": {"quests": [odd]}})
                                else:
                                    sources[0]["quests"]["quests"].append(odd)
                                before = self.snapshot()
                                output = self.startup_sources(sources, dry_run=dry_run)
                                if dry_run:
                                    self.assertEqual(self.snapshot(), before)
                                else:
                                    self.assertFalse(QuestDefinition.objects.filter(name="Root").exists())
                                    self.assertEqual(QuestDefinition.objects.filter(name="Odd").exists(), saved and reason == "retired")
                                    if saved:
                                        previous.refresh_from_db()
                                        self.assertEqual(previous.description, "Saved badge")
                                        if reason == "retired":
                                            self.assertEqual(QuestDefinition.objects.get(name="Odd").required_badge_id, previous.pk)
                                    else:
                                        self.assertFalse(Badge.objects.filter(name=str(name)).exists())
                                    if not saved or reason == "conflict":
                                        self.assertIn("Left quest 'Odd' unchanged", output)
                            finally:
                                transaction.set_rollback(True)

    def test_native_coerced_references_follow_withheld_text_badges(self):
        for reference in (5, True, 2.5, ["X"]):
            self.assert_withheld_coercion(reference, str(reference))

    def test_text_reference_follows_a_withheld_scalar_badge_source(self):
        self.assert_withheld_coercion("5", 5)

    def test_text_reference_loads_a_native_scalar_badge_source_without_deferral(self):
        for split in (False, True):
            for dry_run in (False, True):
                with self.subTest(split=split, dry_run=dry_run), transaction.atomic():
                    try:
                        badge = {"name": 5, "criteria_type": "projects_completed", "criteria_value": {"count": 1}}
                        quest = {"name": "Odd", "quest_type": "collection", "target_value": 1, "required_badge": "5"}
                        sources = [{"badges": {"badges": [badge]}}]
                        if split:
                            sources.append({"quests": {"quests": [quest]}})
                        else:
                            sources[0]["quests"] = {"quests": [quest]}
                        before = self.snapshot()
                        self.startup_sources(sources, dry_run=dry_run)
                        if dry_run:
                            self.assertEqual(self.snapshot(), before)
                        else:
                            self.assertEqual(QuestDefinition.objects.get(name="Odd").required_badge_id, Badge.objects.get(name="5").pk)
                    finally:
                        transaction.set_rollback(True)

    def test_changing_component_keeps_native_unhashable_badge_diagnostics(self):
        for reference in (["X"], {"x": 1}):
            for installed in (False, True):
                for split in (False, True):
                    with self.subTest(reference=reference, installed=installed, split=split), transaction.atomic():
                        try:
                            family = make_family(parents=[{"username": "cycle-badge-parent", "is_staff": True}]).family
                            SkillCategory.objects.create(name="Arch", is_retired=True)
                            category = SkillCategory.objects.create(name="Renamed robotics")
                            RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category.pk,
                                family=family, source_lookup={"name": "robotics"}, values={"_authoring": {"version": 1, "source": "mcp"}})
                            for name in ("Q3", "Q6"):
                                QuestDefinition.objects.create(name=name, description="Saved rules", quest_type="collection",
                                    target_value=2, is_system=True, is_repeatable=True)
                            previous = Badge.objects.create(name=str(reference), criteria_type="projects_completed", criteria_value={"count": 1}) if installed else None
                            tree = {"categories": [{"name": "Arch"}, {"name": "Robotics"}],
                                "skills": [{"name": "Fresh", "category": "Arch"}, {"name": "Servo", "category": "Robotics"}]}
                            def quest(name, **values):
                                if values.get("prerequisite_quest"):
                                    values["trigger_filter"] = {"allowed_triggers": ["reading_logged"]}
                                return {"name": name, "quest_type": "collection", "target_value": 2, **values}
                            quests = [quest("Q0", skill_tags=["Arch::Fresh"]), quest("Q1", is_repeatable=True, skill_tags=["Robotics::Servo"]),
                                quest("Q3", is_repeatable=False, required_badge="B3"), quest("Q6", prerequisite_quest="Q8"),
                                quest("Q8", required_badge="B3", prerequisite_quest="Q0"), quest("E"), quest("Odd", required_badge=reference)]
                            badges = {"badges": [{"name": "B3", "criteria_type": "quest_completed", "criteria_value": {"quest_names": ["Q6", "Q3", "Q1"], "count": 3}}]}
                            sources = [{"skill_tree": tree, "badges": badges}]
                            if split:
                                sources.append({"quests": {"quests": quests}})
                            else:
                                sources[0]["quests"] = {"quests": quests}
                            before = self.snapshot()
                            if installed:
                                self.startup_sources(sources)
                                self.assertEqual(QuestDefinition.objects.get(name="Odd").required_badge_id, previous.pk)
                            else:
                                with self.assertRaises(CommandError) as error:
                                    self.startup_sources(sources)
                                self.assertIn("unknown badge or ambiguous source", str(error.exception))
                                self.assertIn(repr(reference), str(error.exception))
                                self.assertEqual(self.snapshot(), before)
                        finally:
                            transaction.set_rollback(True)

    def test_equal_python_scalars_do_not_claim_a_different_native_badge_name(self):
        for reference in (True, 1.0):
            with self.subTest(reference=reference), transaction.atomic():
                try:
                    SkillCategory.objects.create(name="Archive", is_retired=True)
                    source = {"skill_tree": {"categories": [{"name": "Archive"}], "skills": [{"name": "Fresh", "category": "Archive"}]},
                        "badges": {"badges": [{"name": 1, "criteria_type": "quest_completed", "criteria_value": {"quest_names": ["Root"]}}]},
                        "quests": {"quests": [{"name": "Root", "quest_type": "collection", "target_value": 1, "skill_tags": ["Archive::Fresh"]},
                            {"name": "Odd", "quest_type": "collection", "target_value": 1, "required_badge": reference}]}}
                    before = self.snapshot()
                    with self.assertRaises(CommandError) as error:
                        self.startup_sources([source])
                    self.assertIn("unknown badge or ambiguous source", str(error.exception))
                    self.assertIn(repr(reference), str(error.exception))
                    self.assertEqual(self.snapshot(), before)
                finally:
                    transaction.set_rollback(True)

    def test_recorded_badge_refusals_survive_an_absent_source_entry(self):
        for recorded in ("strict", "retired", "cycle-pin"):
            with self.subTest(recorded=recorded), transaction.atomic():
                try:
                    if recorded != "retired":
                        Badge.objects.create(name="Earlier gate", criteria_type="projects_completed", criteria_value={"count": 1})
                    state = StartupDeferrals()
                    state.categories.add("Earlier unavailable category")
                    reason = "Badge source 'Earlier gate' was deferred in an earlier pack."
                    if recorded == "strict":
                        state.badges.add("Earlier gate")
                    elif recorded == "retired":
                        state.withheld_badges.add("Earlier gate")
                    else:
                        state.cycle_pins["badge", "Earlier gate"] = True, reason
                    state.dependency_reasons["badge", "Earlier gate"] = reason
                    source = {"quests": {"quests": [{"name": "Odd", "quest_type": "collection", "target_value": 1,
                        "required_badge": "Earlier gate"}]}}
                    state.source_packs.append(source)
                    with TemporaryDirectory() as directory:
                        path = Path(directory)
                        (path / "quests.yaml").write_text(yaml.safe_dump(source["quests"]))
                        loader = ContentPack(path, defer_retired_references=True, startup_deferrals=state)
                        output = StringIO()
                        loader.load(stdout=output)
                    self.assertFalse(QuestDefinition.objects.filter(name="Odd").exists())
                    self.assertIn("Left quest 'Odd' unchanged", output.getvalue())
                finally:
                    transaction.set_rollback(True)
