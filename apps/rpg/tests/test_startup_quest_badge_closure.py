"""Withheld bundled quest sources cannot introduce impossible badge chains."""
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import timedelta

import yaml
from asgiref.sync import async_to_sync
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, Subject, UserBadge
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestSkillTag
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rpg.content.loader import StartupDeferrals
from apps.rpg.models import ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupQuestBadgeClosureTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "closure-parent", "is_staff": True}]).parents[0]

    def retained(self):
        row = SkillCategory.objects.create(name="Mechatronics")
        RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=row.pk,
            family=self.actor.family, source_lookup={"name": "robotics"},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        return row

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:publish", "mcp:author", "mcp:catalog"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        result = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", result)
        return result

    def quest(self, name, **values):
        return {"name": name, "description": "Synthetic source quest", "quest_type": "collection",
                "target_value": 2, **values}

    def badge(self, name, **rule):
        return {"name": name, "description": "Incoming badge", "criteria_type": "quest_completed", "criteria_value": rule}

    def catalog_snapshot(self):
        return {model: list(model.objects.order_by("pk").values(*[
            field.attname for field in model._meta.concrete_fields
            if field.name not in {"created_at", "updated_at"}]))
            for model in (Badge, QuestDefinition, ItemDefinition)}

    def sources(self):
        return [
            {"badges": {"badges": [self.badge("Root complete", quest_name="Root quest"),
                self.badge("Gate complete", quest_names=["Gated quest"]),
                self.badge("Safe alternative", quest_names=["Root quest", "Safe quest"]),
                self.badge("Enough safe completions", quest_names=["Root quest", "Safe quest"], count=1),
                self.badge("Needs both completions", quest_names=["Root quest", "Safe quest"], count=2),
                self.badge("Repeatable alternative", quest_names=["Root quest", "Repeat quest"], count=200),
                self.badge("Legacy zero", quest_name="Root quest", count=0),
                self.badge("Any completed quests", quest_names=[], count=2)]},
             "quests": {"quests": [self.quest("Gated quest", required_badge="Root complete"),
                self.quest("Transitive gate", required_badge="Gate complete")]},
             "items": {"items": [{"name": "Safe snack", "slug": "closure-safe-food", "item_type": "food"}]}},
            {"skill_tree": {"categories": [{"name": "Robotics"}],
                "skills": [{"name": "Servo", "category": "Robotics"}]},
             "quests": {"quests": [self.quest("Root quest", skill_tags=["Robotics::Servo"]),
                self.quest("Safe quest"), self.quest("Repeat quest", is_repeatable=True)]}},
        ]

    def run_sources(self, sources, *, explicit=False, **options):
        with TemporaryDirectory() as directory:
            paths = []
            for index, source in enumerate(sources):
                path = Path(directory) / f"closure-pack-{index}"
                path.mkdir()
                paths.append(path)
                for section, value in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            output = StringIO()
            with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS",
                       tuple((str(path), "") for path in paths)), patch(
                    "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                call_command("loadrpgcontent", stdout=output,
                    **({"pack": str(paths[0])} if explicit else {}), **options)
            return output.getvalue()

    def test_forward_cross_pack_quest_badge_edges_close_transitively(self):
        self.retained()
        output = self.run_sources(self.sources())
        self.assertFalse(Badge.objects.filter(name__in=["Root complete", "Gate complete", "Needs both completions"]).exists())
        self.assertFalse(QuestDefinition.objects.filter(name__in=["Root quest", "Gated quest", "Transitive gate"]).exists())
        self.assertTrue(ItemDefinition.objects.filter(slug="closure-safe-food").exists())
        self.assertEqual(set(Badge.objects.values_list("name", flat=True)), {"Safe alternative", "Enough safe completions",
            "Repeatable alternative", "Legacy zero", "Any completed quests"})
        self.assertIn("Root complete", output)
        self.assertIn("Transitive gate", output)
        before = self.catalog_snapshot()
        self.run_sources(self.sources())
        self.assertEqual(before, self.catalog_snapshot())

    def test_existing_quest_and_badge_rows_remain_unchanged(self):
        self.retained()
        root = QuestDefinition.objects.create(name="Root quest", description="Saved quest", quest_type="collection", target_value=9, is_system=True)
        badge = Badge.objects.create(name="Root complete", description="Saved badge", criteria_type="quest_completed", criteria_value={"quest_name": root.name})
        UserBadge.objects.create(user=self.actor, badge=badge)
        quest = Quest.objects.create(definition=root, status="completed", reward_items_snapshot=[],
            end_date=timezone.now() + timedelta(days=1))
        QuestParticipant.objects.create(quest=quest, user=self.actor)
        history = {model: list(model.objects.order_by("pk").values()) for model in (UserBadge, Quest, QuestParticipant)}
        before = (QuestDefinition.objects.filter(pk=root.pk).values().get(), Badge.objects.filter(pk=badge.pk).values().get())
        self.run_sources(self.sources())
        self.assertEqual(before, (QuestDefinition.objects.filter(pk=root.pk).values().get(), Badge.objects.filter(pk=badge.pk).values().get()))
        self.assertEqual(history, {model: list(model.objects.order_by("pk").values()) for model in history})

    def test_saved_badge_override_keeps_its_safe_rule_and_durable_name(self):
        self.retained()
        badge = Badge.objects.create(name="Saved safe completion", criteria_type="quest_completed",
            criteria_value={"quest_name": "Safe quest"})
        RPGContentOverride.objects.create(model_label="achievements.badge", object_id=badge.pk,
            family=self.actor.family, source_lookup={"name": "Root complete"},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        before = Badge.objects.filter(pk=badge.pk).values().get()
        self.run_sources(self.sources())
        self.assertEqual(before, Badge.objects.filter(pk=badge.pk).values().get())
        gate = QuestDefinition.objects.get(name="Gated quest")
        self.assertEqual(gate.required_badge_id, badge.pk)
        self.assertTrue(QuestDefinition.objects.filter(name="Transitive gate").exists())

    def test_authored_skill_ignores_stale_source_prerequisites_in_the_plan(self):
        self.retained()
        category = self.wire("create_category", {"name": "Safe"})
        skill = self.wire("create_skill", {"name": "Saved safe skill", "category_id": category["id"]})
        saved = RPGContentOverride.objects.get(model_label="achievements.skill", object_id=skill["id"])
        self.assertEqual(saved.values["prerequisites"], [])
        sources = [
            {"badges": {"badges": [self.badge("Safe completion", quest_name="Safe root")]},
             "quests": {"quests": [self.quest("Safe gate", required_badge="Safe completion")]}},
            {"skill_tree": {"categories": [{"name": "Robotics"}, {"name": "Safe"}], "skills": [
                {"name": "Servo", "category": "Robotics"},
                {"name": "Saved safe skill", "category": "Safe", "prereqs": ["Robotics::Servo"]}]},
             "quests": {"quests": [self.quest("Safe root", skill_tags=["Safe::Saved safe skill"])]}},
        ]
        self.run_sources(sources)
        self.assertTrue(Badge.objects.filter(name="Safe completion").exists())
        self.assertEqual(set(QuestDefinition.objects.values_list("name", flat=True)), {"Safe root", "Safe gate"})
        self.assertFalse(Skill.objects.get(pk=skill["id"]).prerequisites.exists())

    def test_forward_retired_new_child_defers_dependents_but_retains_existing_links(self):
        category = SkillCategory.objects.create(name="Retired practice", is_retired=True)
        old_skill = Skill.objects.create(name="Saved practice", category=category)
        old_quest = QuestDefinition.objects.create(name="Saved root", description="Saved rules", is_system=True,
            quest_type="collection", target_value=2)
        QuestSkillTag.objects.create(quest_definition=old_quest, skill=old_skill)
        sources = [
            {"badges": {"badges": [self.badge("Retired completion", quest_name="Retired root"),
                self.badge("Saved completion", quest_name="Saved root")]},
             "quests": {"quests": [self.quest("Retired gate", required_badge="Retired completion")]}},
            {"skill_tree": {"categories": [{"name": "Retired practice"}], "skills": [
                {"name": "New child", "category": "Retired practice"},
                {"name": "Saved practice", "category": "Retired practice"}]},
             "quests": {"quests": [self.quest("Retired root", skill_tags=["Retired practice::New child"]),
                self.quest("Saved root", skill_tags=["Retired practice::Saved practice"])]}},
        ]
        self.run_sources(sources)
        self.assertFalse(Skill.objects.filter(name="New child").exists())
        self.assertFalse(Badge.objects.filter(name="Retired completion").exists())
        self.assertFalse(QuestDefinition.objects.filter(name__in=["Retired root", "Retired gate"]).exists())
        self.assertTrue(Badge.objects.filter(name="Saved completion").exists())
        self.assertEqual(list(old_quest.skill_tags.values_list("skill_id", flat=True)), [old_skill.pk])
        sources[1]["skill_tree"]["categories"][0]["is_retired"] = False
        self.run_sources(sources)
        self.assertTrue(Skill.objects.filter(name="New child").exists())
        self.assertTrue(Badge.objects.filter(name="Retired completion").exists())
        self.assertEqual(QuestDefinition.objects.filter(name__in=["Retired root", "Retired gate"]).count(), 2)

    def test_an_earlier_pack_restoration_keeps_later_new_choices_available(self):
        SkillCategory.objects.create(name="Restored practice", is_retired=True)
        self.run_sources([
            {"skill_tree": {"categories": [{"name": "Restored practice", "is_retired": False}]},
             "badges": {"badges": [self.badge("Restored completion", quest_name="Restored root")]},
             "quests": {"quests": [self.quest("Restored gate", required_badge="Restored completion")]}},
            {"skill_tree": {"categories": [{"name": "Restored practice"}],
                "skills": [{"name": "New practice", "category": "Restored practice"}]},
             "quests": {"quests": [self.quest("Restored root", skill_tags=["Restored practice::New practice"])]}},
        ])
        self.assertTrue(Badge.objects.filter(name="Restored completion").exists())
        self.assertEqual(QuestDefinition.objects.filter(name__in=["Restored root", "Restored gate"]).count(), 2)

    def test_each_projected_parent_is_checked_independently(self):
        for index, (initial_category, initial_subject, category_flag, subject_flag, blocked) in enumerate([
            (True, True, False, None, True),
            (True, True, None, False, True),
            (True, True, False, False, False),
            (False, False, True, None, True),
            (False, False, None, True, True),
        ]):
            with self.subTest(index=index):
                category = SkillCategory.objects.create(name=f"Mixed practice {index}", is_retired=initial_category)
                Subject.objects.create(name="Practice subject", category=category, is_retired=initial_subject)
                category_source = {"name": category.name}
                subject_source = {"name": "Practice subject", "category": category.name}
                if category_flag is not None:
                    category_source["is_retired"] = category_flag
                if subject_flag is not None:
                    subject_source["is_retired"] = subject_flag
                root, gate, badge = f"Mixed root {index}", f"Mixed gate {index}", f"Mixed completion {index}"
                self.run_sources([
                    {"badges": {"badges": [self.badge(badge, quest_name=root)]},
                     "quests": {"quests": [self.quest(gate, required_badge=badge)]}},
                    {"skill_tree": {"categories": [category_source], "subjects": [subject_source],
                        "skills": [{"name": "New child", "category": category.name, "subject": "Practice subject"}]},
                     "quests": {"quests": [self.quest(root, skill_tags=[f"{category.name}::New child"])]}},
                ])
                self.assertEqual(Skill.objects.filter(name="New child", category=category).exists(), not blocked)
                self.assertEqual(Badge.objects.filter(name=badge).exists(), not blocked)
                self.assertEqual(QuestDefinition.objects.filter(name=root).exists(), not blocked)
                self.assertEqual(QuestDefinition.objects.filter(name=gate).exists(), not blocked)

    def test_retirement_deferrals_preserve_dependencies_on_saved_quests(self):
        for layout in ("later-retired-skill", "same-pack", "forward-pack"):
            with self.subTest(layout=layout):
                practice, archive = f"{layout} practice", f"{layout} archive"
                root, after, missing = (f"{layout} {name}" for name in ("Root", "After", "Missing"))
                done, new_done, missing_done = (f"{layout} {name}" for name in ("Done", "New done", "Missing done"))

                def sources(release=False):
                    root_entry = self.quest(root, description="Updated root" if release else "Saved root",
                        skill_tags=[f"{practice}::Old"] + ([f"{practice}::New" if layout == "later-retired-skill"
                            else f"{archive}::Fresh"] if release else []), is_repeatable=release)
                    first = {"skill_tree": {"categories": [{"name": practice}, {"name": archive}],
                        "skills": [{"name": "Old", "category": practice}, {"name": "New", "category": practice},
                            {"name": "Kept", "category": archive}] + ([{"name": "Fresh", "category": archive}] if release else [])},
                        "quests": {"quests": [root_entry] + ([self.quest(missing, skill_tags=[f"{archive}::Fresh"])] if release else [])}}
                    second = {"badges": {"badges": [dict(self.badge(done, quest_name=root),
                            description="Updated badge" if release else "Saved badge")] + ([
                            self.badge(new_done, quest_name=root), self.badge(missing_done, quest_name=missing),
                            self.badge(f"{layout} Any saved", quest_names=[root, missing]),
                            self.badge(f"{layout} One completion", quest_names=[root, missing], count=1),
                            self.badge(f"{layout} Two completions", quest_names=[root, missing], count=2)] if release else [])},
                        "quests": {"quests": [self.quest(after, prerequisite_quest=root,
                            trigger_filter={"allowed_triggers": ["reading_logged"]},
                            description="Updated dependent" if release else "Saved dependent")] + ([
                            self.quest(f"{layout} New after", prerequisite_quest=root,
                                trigger_filter={"allowed_triggers": ["reading_logged"]}),
                            self.quest(f"{layout} Gate", required_badge=new_done),
                            self.quest(f"{layout} Missing gate", required_badge=missing_done)] if release else [])}}
                    if release and layout == "same-pack":
                        first["badges"] = second["badges"]
                        first["quests"]["quests"].extend(second["quests"]["quests"])
                        return [first]
                    return [second, first] if release and layout == "forward-pack" else [first, second]

                self.run_sources(sources())
                saved = QuestDefinition.objects.get(name=root)
                saved_fields = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                saved_tags = list(saved.skill_tags.order_by("pk").values())
                award = UserBadge.objects.create(user=self.actor, badge=Badge.objects.get(name=done))
                completed = Quest.objects.create(definition=saved, status="completed", reward_items_snapshot=[],
                    end_date=timezone.now() + timedelta(days=1))
                participant = QuestParticipant.objects.create(quest=completed, user=self.actor)
                history = [(type(row), row.pk, type(row).objects.filter(pk=row.pk).values().get())
                           for row in (award, completed, participant)]
                SkillCategory.objects.filter(name=archive).update(is_retired=True)
                if layout == "later-retired-skill":
                    Skill.objects.filter(category__name=practice, name="New").update(is_retired=True)

                self.run_sources(sources(True))

                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), saved_fields)
                self.assertEqual(list(saved.skill_tags.order_by("pk").values()), saved_tags)
                self.assertEqual(QuestDefinition.objects.get(name=after).description, "Updated dependent")
                self.assertEqual(Badge.objects.get(name=done).description, "Updated badge")
                self.assertEqual(QuestDefinition.objects.get(name=f"{layout} New after").prerequisite_quest_id, saved.pk)
                self.assertEqual(QuestDefinition.objects.get(name=f"{layout} Gate").required_badge_id,
                    Badge.objects.get(name=new_done).pk)
                self.assertTrue(Badge.objects.filter(name=f"{layout} Any saved").exists())
                self.assertTrue(Badge.objects.filter(name=f"{layout} One completion").exists())
                self.assertFalse(Badge.objects.filter(name__in=[missing_done, f"{layout} Two completions"]).exists())
                self.assertFalse(QuestDefinition.objects.filter(name__in=[missing, f"{layout} Missing gate"]).exists())
                for model, pk, fields in history:
                    self.assertEqual(model.objects.filter(pk=pk).values().get(), fields)
                snapshot = self.catalog_snapshot()
                self.run_sources(sources(True))
                self.assertEqual(self.catalog_snapshot(), snapshot)

    def test_later_conflict_upgrades_retirement_plans_independent_of_source_order(self):
        for layout, conflict in (("after-first", True), ("after-last", True), ("retirement-only", False)):
            with self.subTest(layout=layout):
                retired, category = f"{layout} retired", f"{layout} category"
                root, after, blocked = (f"{layout} {name}" for name in ("Root", "After", "Blocked"))
                badge = f"{layout} Gate badge"
                SkillCategory.objects.create(name=retired, is_retired=True)
                saved = QuestDefinition.objects.create(name=root, description="Saved root",
                    quest_type="collection", target_value=2, is_system=True)
                before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                if conflict:
                    row = SkillCategory.objects.create(name=f"{category} renamed")
                    RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=row.pk,
                        family=self.actor.family, source_lookup={"name": category.upper()},
                        values={"_authoring": {"version": 1, "source": "mcp"}})
                entries = {
                    "after": self.quest(after, prerequisite_quest=root,
                        trigger_filter={"allowed_triggers": ["reading_logged"]}),
                    "root": self.quest(root, description="Rejected edit", required_badge=badge,
                        skill_tags=[f"{retired}::R"]),
                    "blocked": self.quest(blocked, skill_tags=[f"{category}::C"]),
                }
                order = ("blocked", "root", "after") if layout == "after-last" else ("after", "root", "blocked")
                self.run_sources([{"skill_tree": {
                    "categories": [{"name": retired}, {"name": category}],
                    "skills": [{"name": "R", "category": retired}, {"name": "C", "category": category}]},
                    "badges": {"badges": [self.badge(badge, quest_name=blocked)]},
                    "quests": {"quests": [entries[name] for name in order]}}])
                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                self.assertEqual(QuestDefinition.objects.filter(name=after).exists(), not conflict)
                self.assertEqual(Badge.objects.filter(name=badge).exists(), not conflict)

    def test_conflict_flag_upgrades_finish_before_completion_badges_are_written(self):
        self.retained()
        SkillCategory.objects.create(name="Archived upgrade", is_retired=True)
        for name in ("Upgrade root", "Upgrade middle"):
            QuestDefinition.objects.create(name=name, quest_type="collection", target_value=2, is_system=True)
        output = self.run_sources([{"skill_tree": {
            "categories": [{"name": "Archived upgrade"}, {"name": "Robotics"}],
            "skills": [{"name": "R", "category": "Archived upgrade"}, {"name": "Servo", "category": "Robotics"}]},
            "badges": {"badges": [
                self.badge("Upgrade mixed gate", quest_names=["Upgrade middle", "Upgrade missing"], count=2),
                self.badge("Upgrade conflict gate", quest_name="Upgrade conflict"),
                self.badge("Upgrade after complete", quest_name="Upgrade after")]},
            "quests": {"quests": [
                self.quest("Upgrade after", prerequisite_quest="Upgrade root",
                    trigger_filter={"allowed_triggers": ["reading_logged"]}),
                self.quest("Upgrade root", required_badge="Upgrade mixed gate", skill_tags=["Archived upgrade::R"]),
                self.quest("Upgrade middle", required_badge="Upgrade conflict gate", skill_tags=["Archived upgrade::R"]),
                self.quest("Upgrade conflict", skill_tags=["Robotics::Servo"]),
                self.quest("Upgrade missing", skill_tags=["Archived upgrade::R"])]}}])
        self.assertFalse(QuestDefinition.objects.filter(name="Upgrade after").exists())
        self.assertFalse(Badge.objects.filter(name="Upgrade after complete").exists())
        warning = next(line for line in output.splitlines() if "'Upgrade after complete' unchanged:" in line)
        self.assertIn("Skill source 'Robotics::Servo'", warning)

    def test_planned_warnings_retain_the_original_named_source_cause(self):
        for name in ("Alpha", "Beta"):
            row = SkillCategory.objects.create(name=f"Renamed {name}")
            RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=row.pk,
                family=self.actor.family, source_lookup={"name": name.lower()},
                values={"_authoring": {"version": 1, "source": "mcp"}})
        SkillCategory.objects.create(name="Retired route", is_retired=True)
        output = self.run_sources([{"skill_tree": {
            "categories": [{"name": name} for name in ("Alpha", "Beta", "Retired route")],
            "skills": [{"name": "A1", "category": "Alpha"}, {"name": "B1", "category": "Beta"},
                {"name": "Fresh", "category": "Retired route"}]},
            "badges": {"badges": [
                {"name": "Alpha mastery", "criteria_type": "category_mastery",
                    "criteria_value": {"category": "Alpha", "min_level": 1}},
                self.badge("Beta complete", quest_name="Beta root"),
                self.badge("Retired complete", quest_name="Retired root")]},
            "quests": {"quests": [self.quest("Alpha root", skill_tags=["Alpha::A1"]),
                self.quest("Beta root", skill_tags=["Beta::B1"]),
                self.quest("After Alpha", prerequisite_quest="Alpha root",
                    trigger_filter={"allowed_triggers": ["reading_logged"]}),
                self.quest("Retired root", skill_tags=["Retired route::Fresh"]),
                self.quest("Retired gate", required_badge="Retired complete")]}}])
        warnings = [line for line in output.splitlines() if "warning:" in line]
        for name, cause in {
            "Alpha mastery": "Category source 'Alpha'",
            "Alpha root": "Skill source 'Alpha::A1'",
            "After Alpha": "Skill source 'Alpha::A1'",
            "Beta complete": "Skill source 'Beta::B1'",
            "Retired root": "Skill source 'Retired route::Fresh'",
            "Retired gate": "Skill source 'Retired route::Fresh'",
        }.items():
            with self.subTest(name=name):
                warning = next(line for line in warnings if f" {name!r} unchanged:" in line)
                self.assertIn(cause, warning)

    def test_planned_graph_clears_after_success_dry_run_and_failure(self):
        self.retained()
        for mode in ("dry", "failure", "success"):
            state = StartupDeferrals()
            sources = self.sources()
            if mode == "failure":
                sources[1]["quests"]["quests"].append(self.quest("Unknown", required_badge="Missing badge"))
            with self.subTest(mode=mode), patch("apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state):
                if mode == "failure":
                    with self.assertRaises(CommandError):
                        self.run_sources(sources)
                else:
                    self.run_sources(sources, dry_run=mode == "dry")
            self.assertEqual(getattr(state, "source_packs", []), [])
            self.assertEqual((getattr(state, "planned_badges", {}), getattr(state, "planned_quests", {})), ({}, {}))
            self.assertEqual(getattr(state, "dependency_reasons", {}), {})
            self.assertEqual((state.skills, state.conflict_skills, state.categories), (set(), set(), set()))

    def test_clean_sources_load_and_reload_all_rows(self):
        sources = self.sources()
        self.run_sources(sources)
        self.assertEqual(Badge.objects.count(), 8)
        self.assertEqual(QuestDefinition.objects.count(), 5)
        before = self.catalog_snapshot()
        self.run_sources(sources)
        self.assertEqual(before, self.catalog_snapshot())

    def test_unrelated_unknown_references_still_fail_and_roll_back(self):
        self.retained()
        for addition in (self.quest("Invalid skill", skill_tags=["Unknown::Practice"]),
                         self.quest("Invalid badge", required_badge="Unknown badge")):
            sources = deepcopy(self.sources())
            sources[1]["quests"]["quests"].append(addition)
            with self.subTest(addition=addition), self.assertRaises(CommandError):
                self.run_sources(sources)
            self.assertFalse(ItemDefinition.objects.exists())
            self.assertFalse(Badge.objects.exists())
            self.assertFalse(QuestDefinition.objects.exists())

    def test_explicit_conflict_names_source_retainer_and_pack_without_partial_writes(self):
        self.retained()
        source = {"skill_tree": {"categories": [{"name": "Safe first"}, {"name": "Robotics"}]}}
        for options in ({}, {"dry_run": True}, {"namespace": "private-"}):
            with self.subTest(options=options), self.assertRaises(CommandError) as caught:
                self.run_sources([source], explicit=True, **options)
            message = str(caught.exception)
            self.assertIn("Robotics", message)
            self.assertIn("Mechatronics", message)
            self.assertIn("closure-pack-0", message)
            self.assertFalse(SkillCategory.objects.filter(name="Safe first").exists())

    def test_retirement_deferrals_preserve_dependencies_on_saved_badges(self):
        from apps.achievements import criteria

        for layout in ("same-pack", "later-pack", "forward-pack"):
            with self.subTest(layout=layout):
                root, missing, badge, gate, new_gate, chained, completion = (
                    f"{layout} badge {name}" for name in
                    ("Root", "Missing", "Saved", "Gate", "New gate", "Chained", "Completion"))
                practice, archive = f"{layout} Badge practice", f"{layout} Badge archive"

                def sources(release=False):
                    first = {"skill_tree": {"categories": [{"name": practice}, {"name": archive}],
                        "skills": [{"name": "Old", "category": practice}, {"name": "Kept", "category": archive}]
                        + ([{"name": "Fresh", "category": archive}] if release else [])},
                        "badges": {"badges": [dict(self.badge(badge, quest_name=missing if release else root),
                            description="Rejected badge edit" if release else "Saved badge rule")]},
                        "quests": {"quests": [self.quest(root, skill_tags=[f"{practice}::Old"])]
                            + ([self.quest(missing, skill_tags=[f"{archive}::Fresh"])] if release else [])}}
                    second = {"quests": {"quests": [self.quest(gate, required_badge=badge,
                        description="Updated dependent" if release else "Saved dependent")]
                        + ([self.quest(new_gate, required_badge=badge),
                            self.quest(chained, required_badge=completion)] if release else [])}}
                    if release:
                        second["badges"] = {"badges": [self.badge(completion, quest_name=new_gate)]}
                    if layout == "same-pack":
                        first["quests"]["quests"].extend(second["quests"]["quests"])
                        first["badges"]["badges"].extend(second.get("badges", {}).get("badges", []))
                        return [first]
                    return [second, first] if release and layout == "forward-pack" else [first, second]

                self.run_sources(sources())
                saved_badge = Badge.objects.get(name=badge)
                saved_gate = QuestDefinition.objects.get(name=gate)
                saved_root = QuestDefinition.objects.get(name=root)
                before_badge = Badge.objects.filter(pk=saved_badge.pk).values().get()
                earned = UserBadge.objects.create(user=self.actor, badge=saved_badge)
                completed = Quest.objects.create(definition=saved_root, status="completed", reward_items_snapshot=[],
                    end_date=timezone.now() + timedelta(days=1))
                participant = QuestParticipant.objects.create(quest=completed, user=self.actor)
                history = [(type(row), row.pk, type(row).objects.filter(pk=row.pk).values().get())
                    for row in (earned, completed, participant)]
                SkillCategory.objects.filter(name=archive).update(is_retired=True)

                output = self.run_sources(sources(True))

                saved_gate.refresh_from_db()
                self.assertEqual(saved_gate.description, "Updated dependent")
                self.assertEqual(saved_gate.required_badge_id, saved_badge.pk)
                self.assertEqual(Badge.objects.filter(pk=saved_badge.pk).values().get(), before_badge)
                self.assertTrue(criteria.check(self.actor, saved_badge))
                self.assertEqual(QuestDefinition.objects.get(name=new_gate).required_badge_id, saved_badge.pk)
                self.assertEqual(QuestDefinition.objects.get(name=chained).required_badge_id,
                    Badge.objects.get(name=completion).pk)
                self.assertFalse(QuestDefinition.objects.filter(name=missing).exists())
                self.assertFalse(Skill.objects.filter(category__name=archive, name="Fresh").exists())
                for model, pk, fields in history:
                    self.assertEqual(model.objects.filter(pk=pk).values().get(), fields)
                warning = next(line for line in output.splitlines() if f" {badge!r} unchanged:" in line)
                self.assertIn(f"Skill source '{archive}::Fresh'", warning)
                self.assertFalse(any(f" {name!r} unchanged:" in output for name in (gate, new_gate, chained, completion)))
                before = self.catalog_snapshot()
                self.run_sources(sources(True))
                self.assertEqual(before, self.catalog_snapshot())

    def test_missing_deferred_badge_and_case_variant_do_not_admit_gates(self):
        for variant in (False, True):
            with self.subTest(case_variant=variant):
                suffix = "case variant" if variant else "missing"
                archive, missing, badge, gate = (f"{suffix} badge {name}" for name in
                    ("Archive", "Missing", "Saved", "Gate"))
                SkillCategory.objects.create(name=archive, is_retired=True)
                if variant:
                    Badge.objects.create(name=badge.upper(), description="Different exact native identity",
                        criteria_type="quest_completed", criteria_value={"quest_name": "Other root"})
                output = self.run_sources([{
                    "skill_tree": {"categories": [{"name": archive}],
                        "skills": [{"name": "Fresh", "category": archive}]},
                    "badges": {"badges": [self.badge(badge, quest_name=missing)]},
                    "quests": {"quests": [self.quest(missing, skill_tags=[f"{archive}::Fresh"]),
                        self.quest(gate, required_badge=badge)]}}])
                self.assertFalse(Badge.objects.filter(name=badge).exists())
                self.assertFalse(QuestDefinition.objects.filter(name__in=[missing, gate]).exists())
                warning = next(line for line in output.splitlines() if f" {gate!r} unchanged:" in line)
                self.assertIn(f"Skill source '{archive}::Fresh'", warning)

    def test_source_conflicts_still_withhold_dependents_of_saved_badges(self):
        self.retained()
        root = QuestDefinition.objects.create(name="Safe badge root", is_system=True,
            quest_type="collection", target_value=2)
        badge = Badge.objects.create(name="Conflict retained badge", description="Saved badge rule",
            criteria_type="quest_completed", criteria_value={"quest_name": root.name})
        gate = QuestDefinition.objects.create(name="Conflict retained gate", description="Saved gate rule",
            required_badge=badge, is_system=True, quest_type="collection", target_value=2)
        before = self.catalog_snapshot()
        output = self.run_sources([{"badges": {"badges": [dict(
                self.badge(badge.name, quest_name="Conflicted badge root"), description="Rejected badge edit")]},
            "quests": {"quests": [self.quest(gate.name, required_badge=badge.name, description="Rejected gate edit"),
                self.quest("Conflict new gate", required_badge=badge.name)]}},
            {"skill_tree": {"categories": [{"name": "Robotics"}],
                "skills": [{"name": "Servo", "category": "Robotics"}]},
             "quests": {"quests": [self.quest("Conflicted badge root", skill_tags=["Robotics::Servo"])]}}])
        self.assertEqual(before, self.catalog_snapshot())
        self.assertFalse(QuestDefinition.objects.filter(name__in=["Conflicted badge root", "Conflict new gate"]).exists())
        warning = next(line for line in output.splitlines() if f" {gate.name!r} unchanged:" in line)
        self.assertIn("Skill source 'Robotics::Servo'", warning)

    def test_saved_badge_false_plans_upgrade_to_conflicts_before_new_gates(self):
        self.retained()
        SkillCategory.objects.create(name="Badge upgrade archive", is_retired=True)
        safe = QuestDefinition.objects.create(name="Badge upgrade safe", is_system=True,
            quest_type="collection", target_value=2)
        roots = [f"Badge upgrade root {index}" for index in range(4)]
        badges = [f"Badge upgrade saved {index}" for index in range(4)]
        for root, badge in zip(roots, badges):
            QuestDefinition.objects.create(name=root, description="Saved root rule", is_system=True,
                quest_type="collection", target_value=2)
            Badge.objects.create(name=badge, description="Saved badge rule",
                criteria_type="quest_completed", criteria_value={"quest_name": safe.name})
        before = self.catalog_snapshot()
        # Each saved badge first gets a retirement-only plan through Missing.
        # Conflicts then travel right-to-left through the already planned rows.
        incoming = [self.quest("Badge upgrade new gate", required_badge=badges[0])]
        incoming.extend(self.quest(root, required_badge=badges[index + 1] if index < 3 else "Badge upgrade conflict",
            skill_tags=["Badge upgrade archive::Fresh"]) for index, root in enumerate(roots))
        incoming.extend([self.quest("Badge upgrade blocked", skill_tags=["Robotics::Servo"]),
            self.quest("Badge upgrade missing", skill_tags=["Badge upgrade archive::Fresh"])])
        output = self.run_sources([{"skill_tree": {
            "categories": [{"name": "Badge upgrade archive"}, {"name": "Robotics"}],
            "skills": [{"name": "Fresh", "category": "Badge upgrade archive"},
                {"name": "Servo", "category": "Robotics"}]},
            "badges": {"badges": [self.badge(badge, quest_names=[root, "Badge upgrade missing"], count=2)
                for root, badge in zip(roots, badges)]
                + [self.badge("Badge upgrade conflict", quest_name="Badge upgrade blocked")]},
            "quests": {"quests": incoming}}])
        self.assertEqual(before, self.catalog_snapshot())
        self.assertFalse(QuestDefinition.objects.filter(name="Badge upgrade new gate").exists())
        warning = next(line for line in output.splitlines() if "'Badge upgrade new gate' unchanged:" in line)
        self.assertIn("Skill source 'Robotics::Servo'", warning)

    def capacity_order_case(self, prefix, layout, *, saved_repeatable=True, source_repeatable=False,
                            reject=True, depth=0, badge_delay=False, conflicted=False):
        root, missing, badge, any_badge, gate, archive = (f"{prefix} {suffix}" for suffix in
            ("Saved", "Missing", "Two", "Any", "Gate", "Archive"))
        SkillCategory.objects.create(name=archive, is_retired=True)
        saved = QuestDefinition.objects.create(name=root, description="Saved capacity", is_system=True,
            quest_type="collection", target_value=2, is_repeatable=saved_repeatable)
        before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
        reference = missing
        delayed_quests, delayed_badges = [], []
        if not reject:
            reference = f"{prefix} Safe prerequisite"
            QuestDefinition.objects.create(name=reference, quest_type="collection", target_value=2, is_system=True)
        elif badge_delay:
            for index in reversed(range(depth + 1)):
                delayed_badge = f"{prefix} Delayed badge {index}"
                delayed_badges.append(self.badge(delayed_badge, quest_name=reference))
                reference = delayed_badge
                if index:
                    delayed_quest = f"{prefix} Delayed quest {index}"
                    delayed_quests.append(self.quest(delayed_quest, required_badge=reference))
                    reference = delayed_quest
        else:
            for index in reversed(range(depth)):
                delayed = f"{prefix} Prerequisite {index}"
                delayed_quests.append(self.quest(delayed, prerequisite_quest=reference,
                    trigger_filter={"allowed_triggers": ["reading_logged"]}))
                reference = delayed
        edited = self.quest(root, description="Applied capacity", is_repeatable=source_repeatable,
            **({} if not reject else {"required_badge": reference} if badge_delay else
               {"prerequisite_quest": reference, "trigger_filter": {"allowed_triggers": ["reading_logged"]}}))
        root_entry = self.quest(missing, skill_tags=[f"{archive}::Fresh"])
        tree = {"categories": [{"name": archive}], "skills": [{"name": "Fresh", "category": archive}]}
        if conflicted:
            retained = SkillCategory.objects.create(name=f"{prefix} Retained")
            source = f"{prefix} Conflict"
            RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=retained.pk,
                family=self.actor.family, source_lookup={"name": source.upper()},
                values={"_authoring": {"version": 1, "source": "mcp"}})
            tree["categories"].append({"name": source})
            tree["skills"].append({"name": "Blocked", "category": source})
            root_entry = self.quest(missing, skill_tags=[f"{source}::Blocked"])
            # The saved edit is rejected by a separate retired route, so its
            # saved repeatability can still supply the conflicted alternative.
            retired_missing = f"{prefix} Retired missing"
            delayed_quests.append(self.quest(retired_missing, skill_tags=[f"{archive}::Fresh"]))
            if not badge_delay:
                edited["prerequisite_quest"] = retired_missing
        badges = {"badges": [self.badge(badge, quest_names=[missing, root], count=2),
            self.badge(any_badge, quest_names=[missing, root])] + delayed_badges}
        dependent = self.quest(gate, required_badge=badge)
        earlier = [edited] + delayed_quests
        if layout == "same-C-first":
            packs = [{"skill_tree": tree, "badges": badges,
                "quests": {"quests": earlier + [root_entry, dependent]}}]
        elif layout == "same-P-first":
            packs = [{"skill_tree": tree, "badges": badges,
                "quests": {"quests": [root_entry] + list(reversed(delayed_quests)) + [edited, dependent]}}]
        else:
            choices = {"P": {"skill_tree": tree, "quests": {"quests": [root_entry]}},
                "C": {"quests": {"quests": earlier}},
                "B": {"badges": badges, "quests": {"quests": [dependent]}}}
            packs = [choices[key] for key in {"cross-B-C-P": "BCP", "cross-P-B-C": "PBC",
                "cross-C-P-B": "CPB"}[layout]]
        return packs, saved, before, badge, any_badge, gate, missing

    def test_completion_capacity_uses_retained_quest_in_every_source_order(self):
        from apps.achievements import criteria

        for layout in ("same-C-first", "same-P-first", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
            with self.subTest(layout=layout):
                packs, saved, before, badge, any_badge, gate, missing = self.capacity_order_case(layout, layout)
                history = []
                for _ in range(2):
                    completed = Quest.objects.create(definition=saved, status="completed", reward_items_snapshot=[],
                        end_date=timezone.now() + timedelta(days=1))
                    participant = QuestParticipant.objects.create(quest=completed, user=self.actor)
                    history.extend((type(row), row.pk, type(row).objects.filter(pk=row.pk).values().get())
                        for row in (completed, participant))
                self.run_sources(packs)
                self.assertTrue(Badge.objects.filter(name=badge).exists())
                self.assertTrue(Badge.objects.filter(name=any_badge).exists())
                self.assertEqual(QuestDefinition.objects.get(name=gate).required_badge_id, Badge.objects.get(name=badge).pk)
                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                self.assertFalse(QuestDefinition.objects.filter(name=missing).exists())
                self.assertTrue(criteria.check(self.actor, Badge.objects.get(name=badge)))
                for model, pk, fields in history:
                    self.assertEqual(model.objects.filter(pk=pk).values().get(), fields)
                before_reload = self.catalog_snapshot()
                self.run_sources(packs)
                self.assertEqual(self.catalog_snapshot(), before_reload)

    def test_completion_capacity_follows_applied_or_rejected_source_edit(self):
        cases = [(True, False, False, False), (False, True, True, False), (False, True, False, True),
                 (False, False, True, False), (True, True, True, True)]
        for index, (saved_repeatable, source_repeatable, reject, expected) in enumerate(cases):
            for layout in ("same-C-first", "same-P-first", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
                with self.subTest(case=index, layout=layout):
                    prefix = f"Capacity matrix {index} {layout}"
                    packs, saved, before, badge, any_badge, gate, missing = self.capacity_order_case(prefix, layout,
                        saved_repeatable=saved_repeatable, source_repeatable=source_repeatable, reject=reject)
                    self.run_sources(packs)
                    self.assertEqual(Badge.objects.filter(name=badge).exists(), expected)
                    self.assertEqual(QuestDefinition.objects.filter(name=gate).exists(), expected)
                    self.assertTrue(Badge.objects.filter(name=any_badge).exists())
                    self.assertFalse(QuestDefinition.objects.filter(name=missing).exists())
                    saved.refresh_from_db()
                    if reject:
                        self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                    else:
                        self.assertEqual(saved.description, "Applied capacity")
                        self.assertEqual(saved.is_repeatable, source_repeatable)

    def test_completion_capacity_waits_for_long_prerequisite_and_badge_gate_rejections(self):
        for mode, depth in (("prerequisite", 5), ("badge", 4)):
            for layout in ("same-C-first", "same-P-first", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
                with self.subTest(mode=mode, layout=layout):
                    prefix = f"Delayed {mode} {layout}"
                    packs, saved, before, badge, _any, gate, missing = self.capacity_order_case(prefix, layout,
                        depth=depth, badge_delay=mode == "badge")
                    self.run_sources(packs)
                    self.assertTrue(Badge.objects.filter(name=badge).exists())
                    self.assertTrue(QuestDefinition.objects.filter(name=gate).exists())
                    self.assertFalse(QuestDefinition.objects.filter(name=missing).exists())
                    self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)

    def test_transient_conflict_badge_plan_retracts_after_saved_capacity_is_known(self):
        for layout in ("same-C-first", "same-P-first", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
            with self.subTest(layout=layout):
                prefix = f"Transient conflict {layout}"
                packs, saved, before, badge, _any, gate, missing = self.capacity_order_case(prefix, layout,
                    depth=3, conflicted=True)
                self.run_sources(packs)
                self.assertTrue(Badge.objects.filter(name=badge).exists())
                self.assertTrue(QuestDefinition.objects.filter(name=gate).exists())
                self.assertFalse(QuestDefinition.objects.filter(name=missing).exists())
                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)

    def capacity_cycle_case(self, prefix, layout):
        root, missing, badge, outside, blocked_gate, safe_gate, archive = (
            f"{prefix} {suffix}" for suffix in ("Saved", "Missing", "Cycle", "Outside", "Blocked gate", "Safe gate", "Archive"))
        if layout == "same-name":
            badge = root  # Badge and quest names are distinct native identities.
        saved = QuestDefinition.objects.create(name=root, description="Saved cycle rule", is_system=True,
            quest_type="collection", target_value=2, is_repeatable=True)
        SkillCategory.objects.create(name=archive, is_retired=True)
        tree = {"categories": [{"name": archive}], "skills": [{"name": "Fresh", "category": archive}]}
        edited = self.quest(root, description="Conditional edit", is_repeatable=False, required_badge=badge)
        unavailable = self.quest(missing, skill_tags=[f"{archive}::Fresh"])
        badges = {"badges": [self.badge(badge, quest_names=[missing, root], count=2),
            self.badge(outside, quest_names=[missing, root], count=2)]}
        gates = [self.quest(blocked_gate, required_badge=badge), self.quest(safe_gate, required_badge=outside),
            self.quest(f"{prefix} Independent")]
        choices = {"P": {"skill_tree": tree, "quests": {"quests": [unavailable]}},
            "C": {"quests": {"quests": [edited]}},
            "B": {"badges": badges, "quests": {"quests": gates},
                "items": {"items": [{"name": "Independent cycle snack", "slug": prefix.lower().replace(" ", "-") + "-snack",
                    "item_type": "food"}]}}}
        if layout in ("same-C-first", "same-P-first", "same-name"):
            packs = [{"skill_tree": tree, "badges": badges, "items": choices["B"]["items"],
                "quests": {"quests": ([unavailable, edited] if layout == "same-P-first" else [edited, unavailable]) + gates}}]
        else:
            packs = [choices[key] for key in {"cross-B-C-P": "BCP", "cross-P-B-C": "PBC", "cross-C-P-B": "CPB"}[layout]]
        return packs, saved, badge, outside, blocked_gate, safe_gate

    def test_capacity_cycles_pin_only_conditional_sources_across_pack_orders_and_reloads(self):
        for layout in ("same-C-first", "same-P-first", "same-name", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
            with self.subTest(layout=layout):
                prefix = f"Cycle {layout}"
                packs, saved, badge, outside, blocked_gate, safe_gate = self.capacity_cycle_case(prefix, layout)
                before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                state, pins = StartupDeferrals(), []
                original_clear = state.clear

                def capture_and_clear():
                    pins.append(deepcopy(state.cycle_pins))
                    original_clear()

                with patch("apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state), patch.object(
                        state, "clear", side_effect=capture_and_clear):
                    self.run_sources(packs)
                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                self.assertFalse(Badge.objects.filter(name=badge).exists())
                self.assertFalse(QuestDefinition.objects.filter(name=blocked_gate).exists())
                self.assertTrue(Badge.objects.filter(name=outside).exists())
                self.assertEqual(QuestDefinition.objects.get(name=safe_gate).required_badge_id,
                    Badge.objects.get(name=outside).pk)
                self.assertTrue(QuestDefinition.objects.filter(name=f"{prefix} Independent").exists())
                self.assertTrue(ItemDefinition.objects.filter(slug=prefix.lower().replace(" ", "-") + "-snack").exists())
                self.assertEqual(set(pins[-1]), {("badge", badge), ("quest", saved.name)})
                self.assertTrue(all(not flag for flag, _reason in pins[-1].values()))
                self.assertEqual(state.cycle_pins, {})
                self.assertEqual(state.dependency_reasons, {})
                after = self.catalog_snapshot()
                self.run_sources(packs)
                self.assertEqual(after, self.catalog_snapshot())

    def test_capacity_cycle_pins_clear_on_dry_run_and_unrelated_failure(self):
        for mode in ("dry", "failure"):
            with self.subTest(mode=mode):
                packs, saved, _badge, _outside, _blocked, _safe = self.capacity_cycle_case(f"Cycle cleanup {mode}", "same-C-first")
                state = StartupDeferrals()
                before = self.catalog_snapshot()
                if mode == "failure":
                    packs[0]["quests"]["quests"].append(self.quest("Unrelated cycle error", required_badge="Unknown badge"))
                with patch("apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state):
                    if mode == "failure":
                        with self.assertRaises(CommandError):
                            self.run_sources(packs)
                    else:
                        self.run_sources(packs, dry_run=True)
                self.assertEqual(self.catalog_snapshot(), before)
                self.assertEqual(state.cycle_pins, {})
                self.assertEqual(state.planned_badges, {})
                self.assertEqual(state.planned_quests, {})
                self.assertEqual(state.dependency_reasons, {})
                saved.refresh_from_db()
                self.assertTrue(saved.is_repeatable)

    def test_downstream_cycle_keeps_constant_capacity_and_saved_backedges_available(self):
        for backedge in (False, True):
            for layout in ("same-C-first", "same-P-first", "cross-B-C-P", "cross-P-B-C", "cross-C-P-B"):
                with self.subTest(backedge=backedge, layout=layout):
                    prefix = f"Downstream {backedge} {layout}"
                    packs, saved, badge, outside, blocked_gate, safe_gate = self.capacity_cycle_case(prefix, layout)
                    downstream = QuestDefinition.objects.create(name=f"{prefix} Saved downstream", description="Saved downstream",
                        is_system=True, quest_type="collection", target_value=2, is_repeatable=False)
                    for pack in packs:
                        for entry in pack.get("badges", {}).get("badges", []):
                            if entry["name"] == outside:
                                entry["criteria_value"]["quest_names"].append(downstream.name)
                                entry["criteria_value"]["count"] = 3
                        for entry in pack.get("quests", {}).get("quests", []):
                            if backedge and entry["name"] == saved.name:
                                entry["prerequisite_quest"] = downstream.name
                                entry["trigger_filter"] = {"allowed_triggers": ["reading_logged"]}
                    packs[-1].setdefault("quests", {}).setdefault("quests", []).append(self.quest(downstream.name,
                        description="Updated downstream", is_repeatable=False, required_badge=outside))
                    state, final_state = StartupDeferrals(), []
                    original_clear = state.clear

                    def capture_and_clear():
                        final_state.append((deepcopy(state.cycle_pins), deepcopy(state.dependency_reasons)))
                        original_clear()

                    before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                    with patch("apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state), patch.object(
                            state, "clear", side_effect=capture_and_clear):
                        self.run_sources(packs)
                    self.assertTrue(Badge.objects.filter(name=outside).exists())
                    self.assertTrue(QuestDefinition.objects.filter(name=safe_gate).exists())
                    self.assertFalse(Badge.objects.filter(name=badge).exists())
                    self.assertFalse(QuestDefinition.objects.filter(name=blocked_gate).exists())
                    downstream.refresh_from_db()
                    self.assertEqual(downstream.description, "Updated downstream")
                    self.assertFalse(downstream.is_repeatable)
                    self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                    self.assertEqual(set(final_state[-1][0]), {("badge", badge), ("quest", saved.name)})
                    self.assertNotIn(("badge", outside), final_state[-1][1])
                    self.assertNotIn(("quest", downstream.name), final_state[-1][1])
                    after = self.catalog_snapshot()
                    self.run_sources(packs)
                    self.assertEqual(after, self.catalog_snapshot())

    def test_actual_badge_refusal_remains_a_seed_after_later_capacity_changes(self):
        for pack_count in (2, 3):
            with self.subTest(pack_count=pack_count):
                prefix = f"Actual badge refusal {pack_count}"
                archive = SkillCategory.objects.create(name=f"{prefix} Archive", is_retired=True)
                Skill.objects.create(category=archive, name="Old")
                saved = QuestDefinition.objects.create(name=f"{prefix} Saved", description="Saved repeatability",
                    quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
                before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                missing, badge, gate = (f"{prefix} {suffix}" for suffix in ("Missing", "Badge", "Gate"))
                packs = [{"skill_tree": {"categories": [{"name": archive.name}],
                    "skills": [{"name": "Fresh", "category": archive.name}]},
                    "badges": {"badges": [self.badge(badge, quest_names=[missing, saved.name], count=2)]},
                    "quests": {"quests": [self.quest(missing, skill_tags=[f"{archive.name}::Fresh"]),
                        self.quest(saved.name, skill_tags=[f"{archive.name}::Old"])]}}]
                if pack_count == 3:
                    packs.append({"quests": {"quests": [self.quest(f"{prefix} Independent")]}})
                packs.append({"quests": {"quests": [self.quest(gate, required_badge=badge)]}})
                for _reload in range(2):
                    error = None
                    try:
                        output = self.run_sources(packs)
                    except CommandError as exc:
                        error = str(exc)
                    self.assertIsNone(error, "A completed badge refusal must survive later planning passes")
                    self.assertFalse(Badge.objects.filter(name=badge).exists())
                    self.assertFalse(QuestDefinition.objects.filter(name=gate).exists())
                    self.assertIn("Left quest '" + gate + "' unchanged", output)
                    self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)

    def test_badge_written_in_this_batch_is_not_a_retained_rejected_edit(self):
        for saved_badge in (False, True):
            for pack_count in (2, 3):
                with self.subTest(saved_badge=saved_badge, pack_count=pack_count):
                    prefix = f"Applied badge {saved_badge} {pack_count}"
                    archive = SkillCategory.objects.create(name=f"{prefix} Archive")
                    Skill.objects.create(category=archive, name="Old", is_retired=True)
                    root, badge_name, gate = (f"{prefix} {suffix}" for suffix in ("Root", "Badge", "Gate"))
                    if saved_badge:
                        Badge.objects.create(name=badge_name, criteria_type="quest_completed", criteria_value={"quest_name": "Seed"})
                    badge_pack = {"badges": {"badges": [self.badge(badge_name, quest_name=root)]}}
                    root_pack = {"quests": {"quests": [self.quest(root, skill_tags=[f"{archive.name}::Old"])]}}
                    if pack_count == 2:
                        packs = [{**badge_pack, **root_pack}]
                    else:
                        packs = [badge_pack, root_pack]
                    packs.append({"quests": {"quests": [self.quest(gate, required_badge=badge_name)]}})
                    for _reload in range(2):
                        output = self.run_sources(packs)
                        self.assertFalse(QuestDefinition.objects.filter(name=root).exists())
                        self.assertFalse(QuestDefinition.objects.filter(name=gate).exists())
                        self.assertEqual(Badge.objects.get(name=badge_name).criteria_value, {"quest_name": root})
                        self.assertIn("Quest source '" + root + "' was deferred:", output)

    def test_cyclic_transient_conflicts_do_not_override_settled_retirement_refusals(self):
        self.retained()
        for depth in (1, 2, 4):
            for layout in ("forward", "reverse", "split"):
                with self.subTest(depth=depth, layout=layout):
                    prefix = f"Cyclic transient {depth} {layout}"
                    archive = SkillCategory.objects.create(name=f"{prefix} Archive", is_retired=True)
                    saved = QuestDefinition.objects.create(name=f"{prefix} Saved", description="Retained repeatable",
                        quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
                    before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                    missing, conflict, badge, gate, after = (f"{prefix} {suffix}" for suffix in
                        ("Missing", "Conflict", "Badge", "Gate", "After"))
                    roots = [self.quest(missing, skill_tags=[f"{archive.name}::Fresh"]),
                        self.quest(conflict, skill_tags=["Robotics::Servo"])]
                    parent = missing
                    for index in range(depth - 1):
                        name = f"{prefix} Prerequisite {index}"
                        roots.append(self.quest(name, prerequisite_quest=parent,
                            trigger_filter={"allowed_triggers": ["reading_logged"]}))
                        parent = name
                    conditional = self.quest(saved.name, prerequisite_quest=parent, required_badge=badge,
                        trigger_filter={"allowed_triggers": ["reading_logged"]})
                    badges = {"badges": [self.badge(badge, quest_names=[conflict, saved.name], count=2)]}
                    dependents = [self.quest(gate, required_badge=badge), self.quest(after, prerequisite_quest=saved.name,
                        trigger_filter={"allowed_triggers": ["reading_logged"]})]
                    tree = {"categories": [{"name": archive.name}, {"name": "Robotics"}],
                        "skills": [{"name": "Fresh", "category": archive.name}, {"name": "Servo", "category": "Robotics"}]}
                    if layout == "split":
                        packs = [{"badges": badges}, {"quests": {"quests": [conditional, *dependents]}},
                            {"skill_tree": tree, "quests": {"quests": roots}}]
                    else:
                        entries = [*roots, conditional, *dependents]
                        packs = [{"skill_tree": tree, "badges": badges,
                            "quests": {"quests": entries if layout == "forward" else list(reversed(entries))}}]
                    for _reload in range(2):
                        output = self.run_sources(packs)
                        self.assertTrue(Badge.objects.filter(name=badge).exists())
                        self.assertTrue(QuestDefinition.objects.filter(name=gate).exists())
                        self.assertTrue(QuestDefinition.objects.filter(name=after).exists())
                        self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                        self.assertNotIn("Left badge '" + badge + "' unchanged", output)

    def test_varying_downstream_cycles_settle_after_their_upstream_choice(self):
        for layout in ("same-C-first", "same-P-first", "cross-B-C-P"):
            with self.subTest(layout=layout):
                prefix = f"Varying downstream {layout}"
                packs, saved, badge, outside, _blocked, safe_gate = self.capacity_cycle_case(prefix, layout)
                missing = f"{prefix} Missing"
                downstream = QuestDefinition.objects.create(name=f"{prefix} Downstream", description="Saved downstream",
                    quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
                for pack in packs:
                    for entry in pack.get("badges", {}).get("badges", []):
                        if entry["name"] == outside:
                            entry["criteria_value"] = {"quest_names": [missing, saved.name, downstream.name], "count": 3}
                packs[-1].setdefault("quests", {}).setdefault("quests", []).append(self.quest(downstream.name,
                    description="Applied downstream", is_repeatable=False, required_badge=outside))
                for _reload in range(2):
                    self.run_sources(packs)
                    self.assertFalse(Badge.objects.filter(name=badge).exists())
                    self.assertTrue(Badge.objects.filter(name=outside).exists())
                    self.assertTrue(QuestDefinition.objects.filter(name=safe_gate).exists())
                    downstream.refresh_from_db()
                    self.assertEqual(downstream.description, "Applied downstream")
                    self.assertFalse(downstream.is_repeatable)
                    saved.refresh_from_db()
                    self.assertTrue(saved.is_repeatable)

    def test_chained_capacity_cycles_do_not_restart_settled_source_components(self):
        import sys
        from apps.rpg.content.loader import ContentPack

        archive = SkillCategory.objects.create(name="Budget archive", is_retired=True)
        roots = [self.quest("Budget root", required_skill=f"{archive.name}::Fresh", required_skill_level=1)]
        badges, parent = [], "Budget root"
        for index in range(50):
            badge, child = f"Budget lead badge {index}", f"Budget lead quest {index}"
            badges.append(self.badge(badge, quest_name=parent))
            roots.append(self.quest(child, required_badge=badge))
            parent = child
        for index in range(40):
            missing, saved, badge = (f"Budget cycle {index} {suffix}" for suffix in ("Missing", "Saved", "Badge"))
            QuestDefinition.objects.create(name=saved, quest_type="collection", target_value=2,
                is_system=True, is_repeatable=True)
            dependency = ({"prerequisite_quest": parent, "trigger_filter": {"allowed_triggers": ["reading_logged"]}}
                if index == 0 else {"required_badge": parent})
            roots.extend([self.quest(missing, **dependency),
                self.quest(saved, required_badge=badge, is_repeatable=False)])
            badges.append(self.badge(badge, quest_names=[missing, saved], count=2))
            parent = badge
        parsed = {"skill_tree": {"categories": [{"name": archive.name}],
            "skills": [{"name": "Fresh", "category": archive.name}]},
            "quests": {"quests": roots}, "badges": {"badges": badges}}
        counts = {"badge": 0}
        previous = sys.getprofile()

        def observe(frame, event, arg):
            if event == "call" and frame.f_code.co_name == "blocked_badge":
                counts["badge"] += 1

        with TemporaryDirectory() as directory:
            path = Path(directory)
            for section, value in parsed.items():
                (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            state = StartupDeferrals()
            loader = ContentPack(path, defer_retired_references=True, startup_deferrals=state)
            try:
                sys.setprofile(observe)
                ContentPack.prepare_startup_dependencies([loader])
            finally:
                sys.setprofile(previous)
            self.assertLessEqual(counts["badge"], 12 * (len(roots) + len(badges)))
            self.assertTrue(all(name in state.planned_badges for name in [b["name"] for b in badges]))
            self.assertEqual(len(state.cycle_pins), 80)

    def test_disconnected_valid_capacity_cycle_applies_its_source_edit(self):
        archive = SkillCategory.objects.create(name="Disconnected archive", is_retired=True)
        saved = QuestDefinition.objects.create(name="Disconnected saved", description="Old source",
            quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
        packs = [{"skill_tree": {"categories": [{"name": archive.name}],
            "skills": [{"name": "Fresh", "category": archive.name}]},
            "badges": {"badges": [self.badge("Disconnected badge", quest_names=[saved.name], count=2)]},
            "quests": {"quests": [self.quest("Disconnected missing", skill_tags=[f"{archive.name}::Fresh"]),
                self.quest(saved.name, description="Applied source", is_repeatable=False, required_badge="Disconnected badge")]}}]
        for _reload in range(2):
            self.run_sources(packs)
            saved.refresh_from_db()
            self.assertEqual(saved.description, "Applied source")
            self.assertFalse(saved.is_repeatable)
            self.assertTrue(Badge.objects.filter(name="Disconnected badge").exists())

    def test_independent_true_conflict_still_upgrades_a_conditional_saved_cycle(self):
        self.retained()
        saved = QuestDefinition.objects.create(name="Strict cycle saved", description="Retained strict source",
            quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
        before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
        packs = [{"skill_tree": {"categories": [{"name": "Robotics"}],
            "skills": [{"name": "Servo", "category": "Robotics"}]},
            "badges": {"badges": [self.badge("Strict cycle badge", quest_names=["Strict cycle conflict", saved.name], count=2)]},
            "quests": {"quests": [self.quest("Strict cycle conflict", skill_tags=["Robotics::Servo"]),
                self.quest(saved.name, prerequisite_quest="Strict cycle conflict", required_badge="Strict cycle badge",
                    trigger_filter={"allowed_triggers": ["reading_logged"]}),
                self.quest("Strict cycle gate", required_badge="Strict cycle badge")]}}]
        for _reload in range(2):
            output = self.run_sources(packs)
            self.assertFalse(Badge.objects.filter(name="Strict cycle badge").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Strict cycle gate").exists())
            self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
            self.assertIn("retained category identity conflict", output)

    def test_coupled_capacity_cycles_select_an_independently_supported_retained_rule(self):
        self.retained()
        for refusal in ("derived", "direct-retirement", "direct-conflict"):
            for layout in ("same", "reverse", "split"):
                with self.subTest(refusal=refusal, layout=layout):
                    prefix = f"Coupled {refusal} {layout}"
                    archive = SkillCategory.objects.create(name=f"{prefix} Archive", is_retired=True)
                    conflict, retired, retained, edited, after, extra, first, second = (
                        f"{prefix} {suffix}" for suffix in
                        ("Conflict", "Retired", "Retained", "Edited", "After", "Extra", "First badge", "Second badge"))
                    saved_rows = {}
                    for name in (retained, edited, extra):
                        saved_rows[name] = QuestDefinition.objects.create(name=name, description="Saved rules",
                            quest_type="collection", target_value=2, is_system=True, is_repeatable=True)
                    before = QuestDefinition.objects.filter(pk=saved_rows[retained].pk).values().get()
                    rule = self.quest(retained, description="Conditional retained edit", is_repeatable=False, required_badge=first)
                    if refusal == "direct-retirement":
                        rule["skill_tags"] = [f"{archive.name}::Fresh"]
                    elif refusal == "direct-conflict":
                        rule["skill_tags"] = ["Robotics::Servo"]
                    entries = [
                        self.quest(conflict, skill_tags=["Robotics::Servo"], required_badge=second,
                            prerequisite_quest=retained, trigger_filter={"allowed_triggers": ["reading_logged"]}),
                        self.quest(retired, skill_tags=[f"{archive.name}::Fresh"], required_badge=second),
                        self.quest(extra, is_repeatable=False, required_badge=first),
                        self.quest(after, required_badge=second, prerequisite_quest=retained,
                            trigger_filter={"allowed_triggers": ["reading_logged"]}),
                        rule,
                        self.quest(edited, description="Applied repeatability", is_repeatable=False, required_badge=second,
                            prerequisite_quest=retained, trigger_filter={"allowed_triggers": ["reading_logged"]}),
                    ]
                    tree = {"categories": [{"name": archive.name}, {"name": "Robotics"}],
                        "skills": [{"name": "Fresh", "category": archive.name}, {"name": "Servo", "category": "Robotics"}]}
                    badges = {"badges": [self.badge(first, quest_names=[retired, edited], count=2),
                        self.badge(second, quest_names=[conflict, retained, edited], count=3)]}
                    if layout == "split":
                        packs = [{"skill_tree": tree, "badges": badges}, {"quests": {"quests": entries}}]
                    else:
                        packs = [{"skill_tree": tree, "badges": badges,
                            "quests": {"quests": entries if layout == "same" else list(reversed(entries))}}]
                    for _reload in range(2):
                        self.run_sources(packs)
                        self.assertFalse(Badge.objects.filter(name=first).exists())
                        self.assertEqual(QuestDefinition.objects.filter(pk=saved_rows[retained].pk).values().get(), before)
                        saved_rows[edited].refresh_from_db()
                        if refusal == "direct-conflict":
                            self.assertFalse(Badge.objects.filter(name=second).exists())
                            self.assertFalse(QuestDefinition.objects.filter(name=after).exists())
                            self.assertTrue(saved_rows[edited].is_repeatable)
                        else:
                            self.assertTrue(Badge.objects.filter(name=second).exists())
                            self.assertTrue(QuestDefinition.objects.filter(name=after).exists())
                            self.assertFalse(saved_rows[edited].is_repeatable)
                            self.assertEqual(saved_rows[edited].description, "Applied repeatability")
