"""Keep futile retained-capacity trials from rescanning a conflict-fed chain."""
from copy import deepcopy
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, Subject
from apps.quests.models import QuestDefinition, QuestSkillTag
from apps.rpg.content.loader import ContentPack, StartupDeferrals
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


def quest(name, **values):
    if values.get("prerequisite_quest"):
        values.setdefault("trigger_filter", {"allowed_triggers": ["reading_logged"]})
    return {"name": name, "quest_type": "collection", "target_value": 3, **values}


def badge(name, names, count=None):
    rule = {"quest_names": names}
    if count is not None:
        rule["count"] = count
    return {"name": name, "criteria_type": "quest_completed", "criteria_value": rule}


def conflict_chain(size):
    quests = [quest("K", skill_tags=["Robotics::Servo"]), quest("H", required_badge="G"),
        quest("X0", skill_tags=["Arch::Fresh"], prerequisite_quest="H")]
    badges = [badge("G", ["K", f"C{size - 1}"])]
    for index in range(size):
        badges.append(badge(f"B{index}", [f"X{index}", f"C{index}"], 2))
        quests.append(quest(f"C{index}", required_badge=f"B{index}", is_repeatable=False))
        if index + 1 < size:
            quests += [quest(f"Y{index}", required_badge=f"B{index}"),
                quest(f"X{index + 1}", prerequisite_quest=f"Y{index}")]
    return {"skill_tree": {
        "categories": [{"name": "Arch"}, {"name": "Robotics"}],
        "skills": [{"name": "Fresh", "category": "Arch"}, {"name": "Servo", "category": "Robotics"}]},
        "quests": {"quests": quests}, "badges": {"badges": badges}}


def prerequisite_backedge_chain(size):
    quests, badges = [], []
    for index in range(size):
        quests += [quest(f"M{index}", target_value=2, **(
            {"required_badge": f"Bc{index - 1}"} if index else {"skill_tags": ["Arch::Fresh"]})),
            quest(f"C{index}", target_value=2, required_badge=f"Bc{index}", is_repeatable=False,
                **({"prerequisite_quest": "D"} if index == 0 else {}))]
        badges.append(badge(f"Bc{index}", [f"M{index}", f"C{index}"], 2))
    quests += [quest("K", target_value=2, skill_tags=["Robotics::Servo"]),
        quest("Q2", target_value=2, required_badge="Bk"), quest("D", target_value=2, required_badge="Bs")]
    badges += [badge("Bk", ["K"]), badge("Bs", [f"C{size - 1}", "Q2"], 1)]
    return {"skill_tree": conflict_chain(1)["skill_tree"],
        "quests": {"quests": quests}, "badges": {"badges": badges}}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupConflictChainWorkTests(TestCase):
    def setUp(self):
        self.actor = make_family("Conflict chain work", parents=[{
            "username": "conflict-chain-work", "is_staff": True}]).parents[0]

    def exercise_chain(self, size, *, prerequisite_backedge=False):
        source = prerequisite_backedge_chain(size) if prerequisite_backedge else conflict_chain(size)
        SkillCategory.objects.create(name="Arch", is_retired=True)
        retained = SkillCategory.objects.create(name="Mechatronics")
        RPGContentOverride.objects.create(
            model_label="achievements.skillcategory", object_id=retained.pk,
            family=self.actor.family, source_lookup={"name": "robotics"},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        QuestDefinition.objects.bulk_create([
            QuestDefinition(name=f"C{index}", quest_type="collection", target_value=2 if prerequisite_backedge else 3,
                is_system=True, is_repeatable=True) for index in range(size)])
        if prerequisite_backedge:
            Badge.objects.create(name="Bs", criteria_type="quest_completed", criteria_value={"quest_names": ["E"]})
        saved = list(QuestDefinition.objects.order_by("name").values())
        counts = {"blocked_badge": 0, "following_plans": 0}

        def profile(frame, event, arg):
            if (event == "call" and frame.f_code.co_name in counts
                    and frame.f_code.co_filename.endswith("content/loader.py")):
                counts[frame.f_code.co_name] += 1

        with TemporaryDirectory() as directory:
            state = StartupDeferrals()
            loader = ContentPack(Path(directory), defer_retired_references=True, startup_deferrals=state)
            loader._parse_all = lambda: deepcopy(source)
            previous = sys.getprofile()
            try:
                sys.setprofile(profile)
                ContentPack.prepare_startup_dependencies([loader])
            finally:
                sys.setprofile(previous)
            plan = {"badges": state.planned_badges.copy(), "quests": state.planned_quests.copy()}
            if prerequisite_backedge:
                expected_badges = {"Bk": True, **{f"Bc{index}": False for index in range(size)}}
                expected = {"K": True, "Q2": True, **{f"C{index}": False for index in range(size)},
                    **{f"M{index}": False for index in range(size)}}
            else:
                expected_badges = {f"B{index}": False for index in range(size)}
                expected = {"K": True, **{f"C{index}": False for index in range(size)},
                    **{f"X{index}": False for index in range(size)},
                    **{f"Y{index}": False for index in range(size - 1)}}
            self.assertEqual(plan["badges"], expected_badges)
            self.assertEqual(plan["quests"], expected)
            self.assertIn("Robotics::Servo", state.dependency_reasons["quest", "K"])
            # Exercise the actual upserts as well as planning. G/H remain
            # reachable through saved capacity; every rejected C edit preserves
            # its complete saved record, including repeatability and its gates.
            loader.load(stdout=StringIO())
            gate, holder_name = ("Bs", "D") if prerequisite_backedge else ("G", "H")
            self.assertEqual(list(Badge.objects.values_list("name", flat=True)), [gate])
            self.assertEqual(set(QuestDefinition.objects.values_list("name", flat=True)),
                {holder_name, *(f"C{index}" for index in range(size))})
            self.assertEqual(list(QuestDefinition.objects.filter(name__startswith="C").order_by("name").values()), saved)
            holder = QuestDefinition.objects.get(name=holder_name)
            self.assertEqual(holder.required_badge.name, gate)
            rule = ({"quest_names": [f"C{size - 1}", "Q2"], "count": 1} if prerequisite_backedge
                else {"quest_names": ["K", f"C{size - 1}"]})
            self.assertEqual(holder.required_badge.criteria_value, rule)
            self.assertFalse(holder.is_repeatable)
            self.assertIsNone(holder.prerequisite_quest_id)
        # Keep every persistent catalog field in the observation. Timestamps are
        # checked above for retained rows, but excluded from cross-run snapshots.
        catalog = {}
        for model in (SkillCategory, Subject, Skill, Badge, QuestDefinition, QuestSkillTag, RPGContentOverride):
            fields = [field.attname for field in model._meta.concrete_fields
                if field.name not in {"created_at", "updated_at"}]
            catalog[model._meta.label_lower] = list(model.objects.order_by("pk").values(*fields))
        return counts, plan, catalog

    def test_conflict_fed_chains_keep_retained_capacity_trials_bounded(self):
        for size in (10, 20):
            with self.subTest(cycles=size):
                sid = transaction.savepoint()
                cache.clear()
                try:
                    counts, _plan, _catalog = self.exercise_chain(size)
                    self.assertGreater(counts["blocked_badge"], 0)
                    self.assertGreater(counts["following_plans"], 0)
                    # The causal oscillation still needs a linear number of
                    # rounds. Replaying that entire chain for each futile
                    # conditional alternative adds another factor of size.
                    self.assertLessEqual(counts["blocked_badge"], 12 * size * size)
                    self.assertLessEqual(counts["following_plans"], 12 * size + 16)
                finally:
                    transaction.savepoint_rollback(sid)
                    cache.clear()

    def test_prerequisite_backedges_keep_necessary_capacity_trials_bounded(self):
        for size in (10, 20):
            with self.subTest(cycles=size):
                sid = transaction.savepoint()
                cache.clear()
                try:
                    counts, _plan, _catalog = self.exercise_chain(size, prerequisite_backedge=True)
                    self.assertGreater(counts["blocked_badge"], 0)
                    self.assertGreater(counts["following_plans"], 0)
                    self.assertLessEqual(counts["blocked_badge"], 12 * size * size)
                    self.assertLessEqual(counts["following_plans"], 12 * size + 16)
                finally:
                    transaction.savepoint_rollback(sid)
                    cache.clear()
