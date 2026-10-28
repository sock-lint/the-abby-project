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
