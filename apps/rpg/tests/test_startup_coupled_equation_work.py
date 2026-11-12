"""Bound repeated equation evaluation inside one coupled startup component."""
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, StartupDeferrals
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family

A, R = "Arch::Fresh", "Robotics::Servo"
TREE = {"categories": [{"name": "Arch"}, {"name": "Robotics"}],
        "skills": [{"name": "Fresh", "category": "Arch"}, {"name": "Servo", "category": "Robotics"}]}

def q(name, **values):
    if values.get("prerequisite_quest"):
        values.setdefault("trigger_filter", {"allowed_triggers": ["reading_logged"]})
    return {"name": name, "quest_type": "collection", "target_value": 2, **values}

def b(name, **rule):
    return {"name": name, "criteria_type": "quest_completed", "criteria_value": rule}

def separate_cycles(k, lead):
    quests = [q("L0", skill_tags=[A])] + [q(f"L{i}", prerequisite_quest=f"L{i - 1}") for i in range(1, lead)]
    badges, saved = [], {}
    up = f"L{lead - 1}" if lead else None
    for i in range(k):
        m, c, bc = f"M{i}", f"C{i}", f"Bc{i}"
        quests.append(q(m, **({"required_badge": f"Bc{i - 1}"} if i else ({"prerequisite_quest": up} if up else {"skill_tags": [A]}))))
        quests.append(q(c, required_badge=bc, is_repeatable=False))
        badges.append(b(bc, quest_names=[m, c], count=2))
        saved[c] = True
    return {"skill_tree": TREE, "quests": {"quests": quests}, "badges": {"badges": badges}}, saved, {}

def one_component_cycles(k, lead):
    """separate_cycles plus a constant conflict-reachable saved back-edge, so every cycle shares one component."""
    source, saved, saved_b = separate_cycles(k, lead)
    quests, badges = source["quests"]["quests"], source["badges"]["badges"]
    quests += [q("K", skill_tags=[R]), q("Free"), q("Q2", required_badge="Bk"), q("D", required_badge="Bs")]
    badges += [b("Bk", quest_names=["K", "Free"]), b("Bs", quest_names=[f"C{k - 1}", "Q2"], count=1)]
    for entry in quests:
        if entry["name"] == "C0":
            entry["prerequisite_quest"] = "D"
            entry["trigger_filter"] = {"allowed_triggers": ["reading_logged"]}
    saved_b = {"Bs": {"quest_names": [f"C{k - 1}", "Q2"], "count": 1}}
    return source, saved, saved_b


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupCoupledEquationWorkTests(TestCase):
    def test_constant_admission_backedges_keep_coupled_planning_work_bounded(self):
        actor = make_family("Coupled equation work", parents=[{
            "username": "coupled-work", "is_staff": True}]).parents[0]
        for size in (10, 20):
            with self.subTest(cycles=size):
                sid = transaction.savepoint()
                cache.clear()
                try:
                    source, saved, saved_badges = one_component_cycles(size, 0)
                    SkillCategory.objects.create(name="Arch", is_retired=True)
                    row = SkillCategory.objects.create(name="Mechatronics")
                    RPGContentOverride.objects.create(
                        model_label="achievements.skillcategory", object_id=row.pk,
                        family=actor.family, source_lookup={"name": "robotics"},
                        values={"_authoring": {"version": 1, "source": "mcp"}})
                    QuestDefinition.objects.bulk_create([
                        QuestDefinition(name=name, quest_type="collection", target_value=2,
                            is_system=True, is_repeatable=repeatable)
                        for name, repeatable in saved.items()])
                    Badge.objects.bulk_create([
                        Badge(name=name, criteria_type="quest_completed", criteria_value=rule)
                        for name, rule in saved_badges.items()])
                    counts = {"blocked_badge": 0, "following_plans": 0}

                    def profile(frame, event, arg):
                        if event == "call" and frame.f_code.co_name in counts:
                            counts[frame.f_code.co_name] += 1

                    with TemporaryDirectory() as directory:
                        state = StartupDeferrals()
                        loader = ContentPack(Path(directory), defer_retired_references=True,
                            startup_deferrals=state)
                        loader._parse_all = lambda: deepcopy(source)
                        previous = sys.getprofile()
                        try:
                            sys.setprofile(profile)
                            ContentPack.prepare_startup_dependencies([loader])
                        finally:
                            sys.setprofile(previous)
                    self.assertEqual(state.planned_badges, {f"Bc{i}": False for i in range(size)})
                    expected_quests = {"L0": False, "K": True}
                    expected_quests.update({f"M{i}": False for i in range(size)})
                    expected_quests.update({f"C{i}": False for i in range(size)})
                    self.assertEqual(state.planned_quests, expected_quests)
                    self.assertIn("Robotics::Servo", state.dependency_reasons["quest", "K"])
                    # Count actual equation evaluations, allowing ample headroom
                    # while rejecting whole-component recomputation each round.
                    self.assertGreater(counts["blocked_badge"], 0)
                    self.assertGreater(counts["following_plans"], 0)
                    self.assertLessEqual(counts["blocked_badge"], 8 * size + 8)
                    self.assertLessEqual(counts["following_plans"], 12 * size + 12)
                finally:
                    transaction.savepoint_rollback(sid)
                    cache.clear()
