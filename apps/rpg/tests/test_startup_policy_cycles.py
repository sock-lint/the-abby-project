"""Late conflict pulses settle without rejecting native-valid content cycles."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields
from datetime import timedelta
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements import criteria
from apps.achievements.models import Badge, SkillCategory
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rpg.content.loader import StartupDeferrals
from apps.rpg.models import ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupPolicyCycleTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "policy-parent", "is_staff": True}]).parents[0]
        SkillCategory.objects.create(name="Archive", is_retired=True)
        retained = SkillCategory.objects.create(name="Mechatronics")
        RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=retained.pk,
            family=self.actor.family, source_lookup={"name": "robotics"},
            values={"_authoring": {"version": 1, "source": "mcp"}})

    @staticmethod
    def quest(name, **values):
        if values.get("prerequisite_quest"):
            values.setdefault("trigger_filter", {"allowed_triggers": ["reading_logged"]})
        return {"name": name, "description": "Source edit", "quest_type": "collection", "target_value": 2, **values}

    @staticmethod
    def badge(name, names, count=None):
        rule = {"quest_names": names}
        if count is not None:
            rule["count"] = count
        return {"name": name, "criteria_type": "quest_completed", "criteria_value": rule}

    @contextmanager
    def isolated_case(self):
        sid = transaction.savepoint()
        try:
            yield
        finally:
            transaction.savepoint_rollback(sid)

    def sources(self, quests, badges, layout):
        tree = {"categories": [{"name": "Archive"}, {"name": "Robotics"}],
            "skills": [{"name": "Fresh", "category": "Archive"}, {"name": "Servo", "category": "Robotics"}]}
        marker = {"items": [{"name": "Unaffected food", "slug": "policy-cycle-food", "item_type": "food"}]}
        if layout == "split":
            return [{"skill_tree": tree, "badges": {"badges": badges}, "items": marker}, {"quests": {"quests": quests}}]
        return [{"skill_tree": tree, "badges": {"badges": badges}, "items": marker,
            "quests": {"quests": quests if layout == "forward" else list(reversed(quests))}}]

    def snapshot(self):
        return {model: list(model.objects.order_by("pk").values(*[
            field.attname for field in model._meta.concrete_fields if field.name not in {"created_at", "updated_at"}]))
            for model in (Badge, QuestDefinition, ItemDefinition)}

    def load(self, sources, *, dry_run=False):
        state, output = StartupDeferrals(), StringIO()
        count, previous = [0], sys.getprofile()
        node_count = sum(len(pack.get("quests", {}).get("quests", [])) + len(pack.get("badges", {}).get("badges", [])) for pack in sources)
        budget = (len(sources) + 1) * (2 * node_count + 1)

        def observe(frame, event, _arg):
            if event == "call" and frame.f_code.co_name == "cycle_roots":
                count[0] += 1
                if count[0] > budget:
                    raise AssertionError("Cycle policy repeated without making bounded progress")

        with TemporaryDirectory() as directory:
            selections = []
            for index, source in enumerate(sources):
                path = Path(directory) / str(index)
                path.mkdir()
                selections.append((str(path), ""))
                for section, value in source.items():
                    (path / f"{section}.yaml").write_text(yaml.safe_dump(value))
            try:
                sys.setprofile(observe)
                with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple(selections)), patch(
                        "apps.rpg.management.commands.loadrpgcontent.StartupDeferrals", return_value=state), patch(
                        "apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
                    call_command("loadrpgcontent", stdout=output, dry_run=dry_run)
            except Exception as exc:
                self.fail(f"Native-valid startup must settle: {type(exc).__name__}: {exc}")
            finally:
                sys.setprofile(previous)
            self.assertTrue(all(not getattr(state, field.name) for field in fields(state)))
        return output.getvalue()

    def pulse(self, shape, *, conflict=False):
        saved = QuestDefinition.objects.create(name="C", description="Saved repeatable", quest_type="collection",
            target_value=2, is_system=True, is_repeatable=True)
        roots = [self.quest("P", skill_tags=["Archive::Fresh"]), self.quest("K", skill_tags=["Robotics::Servo"])]
        conditional = self.quest("C", prerequisite_quest="D", is_repeatable=False,
            **({"skill_tags": ["Robotics::Servo"]} if conflict else {}))
        badges = [self.badge("Z", ["K", "C"], 2)]
        if shape == "self":
            roots.extend([self.quest("E"), self.quest("D0", prerequisite_quest="P"),
                self.quest("D", prerequisite_quest="D0", required_badge="W"), conditional,
                self.quest("I", required_badge="Z"), self.quest("X", prerequisite_quest="I", required_badge="V0")])
            badges.extend([self.badge("V0", ["X"]), self.badge("W", ["X", "E"])])
            expected = {"Z", "V0", "W"}
        elif shape == "multi":
            roots.extend([self.quest("E"), self.quest("D", prerequisite_quest="P", required_badge="W"), conditional,
                self.quest("X2", required_badge="Vy"), self.quest("X", prerequisite_quest="X2", required_badge="Z"),
                self.quest("Y", required_badge="Vx")])
            badges.extend([self.badge("Vx", ["X"]), self.badge("Vy", ["Y"]), self.badge("W", ["Y", "E"])])
            expected = {"Z", "Vx", "Vy", "W"}
        else:
            roots.extend([self.quest("D", prerequisite_quest="P", required_badge="Vx"), conditional,
                self.quest("X2", required_badge="Vx"), self.quest("X", prerequisite_quest="X2", required_badge="Z")])
            badges.append(self.badge("Vx", ["X"]))
            expected = {"Z", "Vx"}
        return saved, roots, badges, expected

    def test_delayed_conflict_pulses_settle_self_and_multigate_cycles(self):
        for shape in ("self", "multi", "no-alternative"):
            for layout in ("forward", "reverse", "split"):
                with self.subTest(shape=shape, layout=layout), self.isolated_case():
                    saved, quests, badges, expected = self.pulse(shape)
                    before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                    sources, snapshot = self.sources(quests, badges, layout), self.snapshot()
                    self.load(sources, dry_run=True)
                    self.assertEqual(self.snapshot(), snapshot)
                    previous = None
                    for _reload in range(2):
                        self.load(sources)
                        self.assertEqual(set(Badge.objects.values_list("name", flat=True)), expected)
                        self.assertTrue(QuestDefinition.objects.filter(name="X").exists())
                        self.assertFalse(QuestDefinition.objects.filter(name__in=["P", "K", "D"]).exists())
                        self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
                        self.assertTrue(ItemDefinition.objects.filter(slug="policy-cycle-food").exists())
                        after = self.snapshot()
                        if previous is not None:
                            self.assertEqual(after, previous)
                        previous = deepcopy(after)

    def test_policy_pins_can_yield_to_an_independently_supported_saved_capacity(self):
        for layout in ("forward", "reverse", "split"):
            with self.subTest(layout=layout), self.isolated_case():
                saved = [QuestDefinition.objects.create(name=name, description="Saved repeatable", quest_type="collection",
                    target_value=2, is_system=True, is_repeatable=True) for name in ("Q3", "Q6")]
                before = QuestDefinition.objects.filter(pk=saved[1].pk).values().get()
                for _completion in range(3):
                    completed = Quest.objects.create(definition=saved[1], status="completed", reward_items_snapshot=[],
                        end_date=timezone.now() + timedelta(days=1))
                    QuestParticipant.objects.create(quest=completed, user=self.actor)
                history = {model: list(model.objects.order_by("pk").values()) for model in (Quest, QuestParticipant)}
                quests = [self.quest("Q0", skill_tags=["Archive::Fresh"]), self.quest("Q1", skill_tags=["Robotics::Servo"]),
                    self.quest("Q8", prerequisite_quest="Q0", required_badge="B3"), self.quest("Q6", prerequisite_quest="Q8"),
                    self.quest("Q3", is_repeatable=False, required_badge="B3"), self.quest("E")]
                sources = self.sources(quests, [self.badge("B3", ["Q6", "Q3", "Q1"], 3)], layout)
                initial = self.snapshot()
                self.load(sources, dry_run=True)
                self.assertEqual(self.snapshot(), initial)
                for _reload in range(2):
                    output = self.load(sources)
                    self.assertTrue(Badge.objects.filter(name="B3").exists())
                    self.assertTrue(criteria.check(self.actor, Badge.objects.get(name="B3")))
                    self.assertEqual({model: list(model.objects.order_by("pk").values()) for model in history}, history)
                    self.assertEqual(QuestDefinition.objects.filter(pk=saved[1].pk).values().get(), before)
                    edited = QuestDefinition.objects.get(name="Q3")
                    self.assertFalse(edited.is_repeatable)
                    self.assertEqual(edited.required_badge.name, "B3")
                    self.assertNotIn("Left badge 'B3' unchanged", output)
                    self.assertNotIn("Left quest 'Q3' unchanged", output)

    def test_actual_conflict_seeds_remain_strict_during_policy_reconsideration(self):
        for layout in ("forward", "split"):
            with self.subTest(layout=layout), self.isolated_case():
                saved, quests, badges, _expected = self.pulse("self", conflict=True)
                before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
                self.load(self.sources(quests, badges, layout))
                self.assertFalse(Badge.objects.filter(name="Z").exists())
                self.assertFalse(QuestDefinition.objects.filter(name__in=["I", "X", "K"]).exists())
                self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
