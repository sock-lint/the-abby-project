"""Authored milestones and Lab overlays compose without inventing availability."""
from django.test import TestCase
from unittest.mock import patch

from apps.achievements.models import Skill, SkillCategory, XP_THRESHOLDS
from apps.quests.models import QuestDefinition
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.challenge_gates import ChallengeGates, GateReferenceError, normalize_challenge_gates
from apps.rpg.progression.engine import Trial
from apps.rpg.tests.test_progression_engine import quiet_config


class NativeChallengeGateDiagnosticTests(TestCase):
    def setUp(self):
        category = SkillCategory.objects.create(name="Language Arts")
        self.reading = Skill.objects.create(name="Reading Comprehension", category=category)
        self.other_skill = Skill.objects.create(name="Other milestone", category=category)
        self.prior = self.quest("Companion", target=3, duration=3)
        self.voyager = self.quest("Voyager", target=20, duration=56,
                                  prerequisite_quest=self.prior, required_skill=self.reading,
                                  required_skill_level=1)

    @staticmethod
    def quest(name, *, target=2, duration=14, **fields):
        return QuestDefinition.objects.create(
            name=name, description="A daily reading challenge", quest_type="collection", is_system=True,
            target_value=target, duration_days=duration,
            trigger_filter={"allowed_triggers": ["reading_logged"]}, **fields,
        )

    def trial(self, mode="current", rules=None):
        return Trial(quiet_config(reading_minutes=10, challenge_gates={
            "mode": mode, "start_date": "2026-01-01", "rules": rules or [],
        }), load_catalog(), 5)

    @staticmethod
    def row(trial, definition):
        return next(q for q in trial.catalog.quests if q.pk == definition.pk)

    def ready(self, trial):
        trial.completed_quests.add(self.prior.pk)
        trial.unlocked.add(self.reading.pk)
        trial.xp[self.reading.pk] = XP_THRESHOLDS[1]

    def test_current_diagnostics_keep_native_skill_locks_and_active_waiting(self):
        trial = self.trial()
        trial.day = 4
        trial.completed_quests.add(self.prior.pk)
        quest = self.row(trial, self.voyager)
        self.assertFalse(trial.challenge_gates.can_offer(quest, trial))
        target = trial.challenge_gates.target_report(quest, trial)
        self.assertTrue(target["temporarily_locked"])
        trial.challenge_gates.visit(trial)
        self.assertEqual(trial.challenge_gates.visits["with_available_challenge"], 0)
        self.assertEqual(trial.challenge_gates.visits["waiting_for_gate"], 1)

    def test_native_predecessor_is_required_even_after_named_skill_is_reached(self):
        trial = self.trial()
        trial.day = 1
        trial.unlocked.add(self.reading.pk)
        trial.xp[self.reading.pk] = XP_THRESHOLDS[1]
        self.assertFalse(trial.challenge_gates.can_offer(self.row(trial, self.voyager), trial))

    def test_native_requirements_and_hypothetical_skill_date_tenure_combine_with_and(self):
        alternate = self.quest("Additional chapter")
        trial = self.trial("milestone_tenure", [{
            "quest_id": self.voyager.pk, "prerequisite_quest_id": alternate.pk,
            "skill_id": self.other_skill.pk, "skill_level": 1, "min_days": 5,
            "available_from": "2026-01-04", "available_until": "2026-01-10",
        }])
        self.ready(trial)
        trial.completed_quests.add(alternate.pk)
        trial.unlocked.add(self.other_skill.pk)
        trial.xp[self.other_skill.pk] = XP_THRESHOLDS[1]
        quest, gates = self.row(trial, self.voyager), trial.challenge_gates
        trial.day = 5
        self.assertFalse(gates.can_offer(quest, trial))
        trial.day = 6
        trial.completed_quests.remove(self.prior.pk)
        self.assertFalse(gates.can_offer(quest, trial))
        trial.completed_quests.add(self.prior.pk)
        trial.completed_quests.remove(alternate.pk)
        self.assertFalse(gates.can_offer(quest, trial))
        trial.completed_quests.add(alternate.pk)
        trial.xp[self.reading.pk] = XP_THRESHOLDS[1] - 1
        self.assertFalse(gates.can_offer(quest, trial))
        trial.xp[self.reading.pk] = XP_THRESHOLDS[1]
        trial.xp[self.other_skill.pk] = 0
        self.assertFalse(gates.can_offer(quest, trial))
        trial.xp[self.other_skill.pk] = XP_THRESHOLDS[1]
        self.assertTrue(gates.can_offer(quest, trial))
        trial.day = 11
        self.assertFalse(gates.can_offer(quest, trial))

    def test_accepted_window_ignores_later_native_and_hypothetical_offering_locks(self):
        trial = self.trial("milestones", [{"quest_id": self.voyager.pk, "available_until": "2026-01-02"}])
        self.ready(trial)
        trial.day = 1
        quest = self.row(trial, self.voyager)
        trial.advance_challenges("reading_logged", {})
        self.assertIn(quest.pk, trial.quest_windows)
        trial.completed_quests.remove(self.prior.pk)
        trial.unlocked.remove(self.reading.pk)
        trial.day = 3
        self.assertTrue(trial.challenge_gates.can_offer(quest, trial))
        target = trial.challenge_gates.target_report(quest, trial)
        self.assertFalse(target["blocked"])
        self.assertFalse(target["temporarily_locked"])
        self.assertFalse(target["expired"])

    def test_expired_native_predecessor_is_blocked_instead_of_playable_or_waiting(self):
        trial = self.trial()
        trial.quest_windows[self.prior.pk] = {"start": 1, "progress": 1, "paid": False}
        trial.day = 4
        quest = self.row(trial, self.voyager)
        target = trial.challenge_gates.target_report(quest, trial)
        self.assertTrue(target["blocked"])
        self.assertEqual(target["blocked_reasons"], ["prerequisite_window_expired"])
        self.assertFalse(target["temporarily_locked"])
        trial.challenge_gates.visit(trial)
        self.assertEqual(trial.challenge_gates.visits["waiting_for_gate"], 0)
        self.assertEqual(trial.challenge_gates.visits["with_available_challenge"], 0)
        self.assertEqual(trial.challenge_gates.visits["exhausted_or_expired"], 1)

    def test_expiry_of_either_distinct_predecessor_blocks_the_joint_policy(self):
        alternate = self.quest("Additional chapter", target=3, duration=3)
        for expired, completed in ((self.prior, alternate), (alternate, self.prior)):
            with self.subTest(expired=expired.name):
                trial = self.trial("milestones", [{"quest_id": self.voyager.pk,
                                                    "prerequisite_quest_id": alternate.pk}])
                self.ready(trial)
                trial.completed_quests.discard(expired.pk)
                trial.completed_quests.add(completed.pk)
                trial.quest_windows[expired.pk] = {"start": 1, "progress": 1, "paid": False}
                trial.day = 4
                self.assertEqual(trial.challenge_gates.blocked_reasons(self.row(trial, self.voyager), trial),
                                 ["prerequisite_window_expired"])

    def test_native_predecessor_expiry_propagates_through_fixed_point(self):
        successor = self.quest("After Voyager", target=1, prerequisite_quest=self.voyager)
        trial = self.trial()
        trial.quest_windows[self.prior.pk] = {"start": 1, "progress": 1, "paid": False}
        trial.day = 4
        blocked = trial.challenge_gates.blocking(trial)
        self.assertEqual(blocked.get(self.voyager.pk), ["prerequisite_window_expired"])
        self.assertEqual(blocked.get(successor.pk), ["prerequisite_path_expired"])

    def test_native_predecessor_offering_date_cannot_follow_successors_last_date(self):
        trial = self.trial("milestones", [
            {"quest_id": self.prior.pk, "available_from": "2026-01-30"},
            {"quest_id": self.voyager.pk, "available_until": "2026-01-20"},
        ])
        self.assertFalse(trial.challenge_gates.temporal_possible(self.voyager.pk))
        target = trial.challenge_gates.target_report(self.row(trial, self.voyager), trial)
        self.assertFalse(target["reachable"])
        self.assertIn("offering_window_cannot_be_reached", target["unreachable_reasons"])

    def test_combined_native_and_hypothetical_direct_cycle_is_rejected(self):
        with self.assertRaisesMessage(GateReferenceError, "cycle"):
            self.trial("milestones", [{"quest_id": self.prior.pk,
                                       "prerequisite_quest_id": self.voyager.pk}])

    def test_shared_native_and_overlay_dag_reuses_temporal_results(self):
        chapters, rules = [], []
        for index in range(22):
            chapter = self.quest(f"DAG chapter {index}", target=1,
                                 prerequisite_quest=chapters[-1] if chapters else None)
            chapters.append(chapter)
            if index >= 2:
                rules.append({"quest_id": chapter.pk, "prerequisite_quest_id": chapters[index - 2].pk,
                              **({"available_from": "2026-01-20"} if index == 2 else {})})
        gates = ChallengeGates(normalize_challenge_gates({"mode": "milestones", "rules": rules}), load_catalog())
        calls = []
        original = gates.earliest_day

        def counted(quest_id):
            calls.append(quest_id)
            return original(quest_id)

        with patch.object(gates, "earliest_day", side_effect=counted):
            self.assertEqual(gates.earliest_day(chapters[-1].pk), 20)
            self.assertTrue(gates.temporal_possible(chapters[-1].pk))
        self.assertLess(len(calls), 150)
