"""Gated forecasts preserve native promises and distinguish waiting from content."""

from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillCategory, XP_THRESHOLDS
from apps.quests.models import QuestDefinition
from apps.rpg.progression.catalog import FrozenRows, load_catalog
from apps.rpg.progression.challenge_gates import GateReferenceError
from apps.rpg.progression.engine import Trial, normalize_config, run_trial, simulate_progression
from apps.rpg.tests.test_progression_engine import quiet_config


class ProgressionChallengeGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = SkillCategory.objects.create(name="Language Arts")
        cls.skill = Skill.objects.create(category=cls.category, name="Reading Comprehension")
        cls.unearned_skill = Skill.objects.create(category=cls.category, name="Unpracticed skill")
        cls.first = QuestDefinition.objects.create(name="First chapter", quest_type="collection", target_value=1,
            duration_days=7, is_system=True, coin_reward=2, xp_reward=0,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        cls.second = QuestDefinition.objects.create(name="Second chapter", quest_type="collection", target_value=2,
            duration_days=7, is_system=True, coin_reward=3, xp_reward=0,
            trigger_filter={"allowed_triggers": ["reading_logged"]})

    def catalog(self):
        return replace(load_catalog(), badges=[])

    def config(self, mode="milestones", **rule):
        return quiet_config(reading_minutes=10, challenge_gates={"mode": mode, "start_date": "2026-01-01",
            "rules": [{"quest_id": self.second.pk, "prerequisite_quest_id": self.first.pk, **rule}]})

    @staticmethod
    def target(report, quest):
        return next(row for row in report["challenge_gates"]["targets"] if row["quest_id"] == quest.pk)

    def test_milestone_waits_for_a_new_fact_and_does_not_replay_old_reading(self):
        trial = Trial(self.config(), self.catalog(), 5)
        trial.daily(1)
        self.assertIn(self.first.pk, trial.completed_quests)
        self.assertNotIn(self.second.pk, trial.quest_windows)
        trial.daily(2)
        self.assertEqual(trial.quest_windows[self.second.pk]["progress"], 1)
        self.assertNotIn(self.second.pk, trial.completed_quests)
        trial.daily(3)
        self.assertIn(self.second.pk, trial.completed_quests)
        target = self.target(trial.report(), self.second)
        self.assertEqual((target["unlock_day"], target["completion_day"]), (2, 3))

    def test_same_day_later_fact_can_unlock_successor_but_not_predecessor_fact(self):
        trial = Trial(self.config(), self.catalog(), 5)
        trial.day = 1
        trial.advance_challenges("reading_logged", {})
        self.assertNotIn(self.second.pk, trial.quest_windows)
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.quest_windows[self.second.pk]["progress"], 1)

    def test_tenure_counts_elapsed_days_and_14_means_day_15(self):
        trial = Trial(self.config("milestone_tenure", min_days=14), self.catalog(), 5)
        for day in range(1, 15):
            trial.daily(day)
        self.assertNotIn(self.second.pk, trial.quest_windows)
        trial.daily(15)
        self.assertEqual(trial.quest_windows[self.second.pk]["start"], 15)
        trial.daily(16)
        self.assertEqual(self.target(trial.report(), self.second)["completion_day"], 16)

    def test_milestones_ignores_tenure_and_current_ignores_all_valid_rules(self):
        milestones = run_trial(self.config("milestones", min_days=365), self.catalog(), 5)
        self.assertEqual(self.target(milestones, self.second)["unlock_day"], 2)
        current = run_trial(self.config("current", min_days=365, skill_id=self.unearned_skill.pk, skill_level=6,
                                        available_from="2028-01-01"), self.catalog(), 5)
        self.assertEqual(self.target(current, self.second)["unlock_day"], 1)
        self.assertEqual(self.target(current, self.second)["completion_day"], 2)

    def test_calendar_window_is_inclusive_and_accepted_duration_is_not_revoked(self):
        config = self.config(available_from="2026-01-03", available_until="2026-01-03")
        trial = Trial(config, self.catalog(), 5)
        trial.daily(1)
        trial.daily(2)
        self.assertNotIn(self.second.pk, trial.quest_windows)
        trial.daily(3)
        self.assertEqual(trial.quest_windows[self.second.pk]["start"], 3)
        trial.daily(4)
        self.assertIn(self.second.pk, trial.completed_quests)
        self.assertFalse(self.target(trial.report(), self.second)["expired"])

    def test_closed_calendar_offering_is_expired_without_a_saved_window(self):
        report = simulate_progression(self.config(available_until="2025-12-31"), catalog=self.catalog())
        target = self.target(report, self.second)
        self.assertEqual(target["unlocked_trials"], 0)
        self.assertEqual(target["expired_trials"], 1)
        self.assertEqual(target["temporarily_locked_trials"], 0)
        self.assertFalse(target["reachable"])
        self.assertIn("offering_window_cannot_be_reached", target["unreachable_reasons"])
        self.assertEqual(report["challenge_gates"]["gate_unreachable_finite_total"], 1)
        self.assertEqual(report["summary"]["finite_content_total"], 2)

    def test_native_skill_and_explicit_predecessor_gates_are_all_required(self):
        badge = Badge.objects.create(name="Native gate", criteria_type="chore_completions",
                                     criteria_value={"count": 1}, award_coins=False, xp_bonus=0)
        QuestDefinition.objects.filter(pk=self.second.pk).update(required_badge=badge)
        catalog = load_catalog()
        config = self.config(skill_id=self.skill.pk, skill_level=1)
        trial = Trial(config, catalog, 5)
        trial.day = 1
        trial.advance_challenges("reading_logged", {})
        trial.badges.add(badge.pk)
        trial.advance_challenges("reading_logged", {})
        self.assertNotIn(self.second.pk, trial.quest_windows)
        trial.xp[self.skill.pk] = XP_THRESHOLDS[1]
        trial.advance_challenges("reading_logged", {})
        self.assertIn(self.second.pk, trial.quest_windows)

    def test_unpracticed_skill_is_unreachable_without_shrinking_finite_denominator(self):
        catalog = self.catalog()
        current = simulate_progression(self.config("current"), catalog=catalog)
        gated = simulate_progression(self.config(skill_id=self.unearned_skill.pk, skill_level=1), catalog=catalog)
        target = self.target(gated, self.second)
        self.assertFalse(target["reachable"])
        self.assertEqual(target["completed_trials"], 0)
        self.assertEqual(gated["summary"]["finite_content_total"], current["summary"]["finite_content_total"])
        self.assertEqual(gated["summary"]["finite_remaining_p50"], 1)
        self.assertEqual(gated["challenge_gates"]["gate_unreachable_finite_total"], 1)

    def test_future_tenure_and_dates_are_temporary_not_permanent_content_loss(self):
        for kwargs in ({"min_days": 365}, {"available_from": "2028-01-01"}):
            with self.subTest(kwargs=kwargs):
                result = simulate_progression(self.config("milestone_tenure", **kwargs), catalog=self.catalog())
                target = self.target(result, self.second)
                self.assertTrue(target["reachable"])
                self.assertEqual(target["temporarily_locked_trials"], 1)
                self.assertEqual(target["expired_trials"], 0)
                self.assertIsNone(target["p50_unlock_days"])
                self.assertEqual(result["challenge_gates"]["gate_unreachable_finite_total"], 0)

    def test_impossible_tenure_and_calendar_combination_is_not_waiting(self):
        result = simulate_progression(self.config("milestone_tenure", min_days=14, available_until="2026-01-10"), catalog=self.catalog())
        self.assertFalse(self.target(result, self.second)["reachable"])
        self.assertEqual(result["challenge_gates"]["visits"]["waiting_for_gate_p50"], 0)

    def test_visit_counters_only_include_active_visit_starts_and_never_call_waiting_content(self):
        QuestDefinition.objects.filter(pk=self.second.pk).update(duration_days=14)
        config = self.config("milestone_tenure", min_days=14)
        config["active_days_per_week"] = 1
        result = simulate_progression(config, catalog=self.catalog())
        visits = result["challenge_gates"]["visits"]
        self.assertEqual(visits["active_visits_p50"], 5)
        # Days 1, 15 and 22 have available unfinished content; day 8 waits, day 29 is exhausted.
        self.assertEqual(visits["with_available_challenge_p50"], 3)
        self.assertEqual(visits["without_available_challenge_p50"], 2)
        self.assertEqual(visits["waiting_for_gate_p50"], 1)
        self.assertEqual(visits["exhausted_or_expired_p50"], 1)
        self.assertIn("not all app activities", result["challenge_gates"]["scope"])

    def test_incompatible_quest_is_explicitly_outside_routine_subset(self):
        QuestDefinition.objects.filter(pk=self.second.pk).update(trigger_filter={"allowed_triggers": ["movement_session"]})
        report = simulate_progression(self.config(), catalog=self.catalog())
        row = self.target(report, self.second)
        self.assertFalse(row["in_native_subset"])
        self.assertFalse(row["reachable"])
        self.assertEqual(row["unreachable_reasons"], ["outside_native_routine_subset"])

    def test_unconfigured_oneoff_remains_available_while_selected_challenge_waits(self):
        third = QuestDefinition.objects.create(name="Always available", quest_type="collection", target_value=20,
            duration_days=30, is_system=True, coin_reward=0, xp_reward=0,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        result = simulate_progression(self.config("milestone_tenure", min_days=14), catalog=self.catalog())
        self.assertEqual(self.target(result, third)["completed_trials"], 1)
        self.assertEqual(result["challenge_gates"]["visits"]["waiting_for_gate_p50"], 0)

    def test_no_queries_or_household_writers_after_detachment(self):
        catalog = self.catalog()
        with self.assertNumQueries(0), patch("apps.rpg.progression.engine.load_catalog", side_effect=AssertionError("No re-read")):
            result = simulate_progression(self.config("milestone_tenure", min_days=14), catalog=catalog)
        self.assertEqual(self.target(result, self.second)["completed_trials"], 1)

    def test_current_mode_preserves_full_native_trial_and_rng_state(self):
        catalog = self.catalog()
        base = quiet_config(reading_minutes=10)
        current = self.config("current", min_days=365, available_from="2028-01-01")
        trial_a, trial_b = Trial(base, catalog, 17), Trial(current, catalog, 17)
        for day in range(1, 31):
            trial_a.daily(day)
            trial_b.daily(day)
        first, second = trial_a.report(), trial_b.report()
        first.pop("challenge_gates")
        second.pop("challenge_gates")
        self.assertEqual(first, second)
        self.assertEqual(trial_a.rng.getstate(), trial_b.rng.getstate())

    def test_malformed_config_is_rejected_even_in_current_mode(self):
        invalid = [None, [], {"mode": "live"}, {"unknown": True}, {"rules": [False]},
            {"start_date": "2026-02-30"}, {"start_date": "20260101"}, {"start_date": "9999-12-31"},
            {"rules": [{"quest_id": True}]}, {"rules": [{"quest_id": self.second.pk, "user_id": 4}]},
            {"rules": [{"quest_id": self.second.pk, "min_days": True}]},
            {"rules": [{"quest_id": self.second.pk, "min_days": 366}]},
            {"rules": [{"quest_id": self.second.pk, "skill_level": 7}]},
            {"rules": [{"quest_id": self.second.pk, "skill_level": 1}]},
            {"rules": [{"quest_id": self.second.pk, "available_from": "2026-02-01", "available_until": "2026-01-01"}]},
            {"rules": [{"quest_id": self.second.pk}, {"quest_id": self.second.pk}]},
            {"rules": [{"quest_id": self.second.pk}] * 21}]
        for policy in invalid:
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                normalize_config(quiet_config(challenge_gates=policy))

    def test_invalid_catalog_references_and_cycles_are_rejected_before_trials_in_current_mode(self):
        catalog = self.catalog()
        rulesets = [
            [{"quest_id": 999999}],
            [{"quest_id": self.second.pk, "skill_id": 999999}],
            [{"quest_id": self.second.pk, "prerequisite_quest_id": 999999}],
            [{"quest_id": self.second.pk, "prerequisite_quest_id": self.second.pk}],
            [{"quest_id": self.second.pk, "prerequisite_quest_id": self.first.pk},
             {"quest_id": self.first.pk, "prerequisite_quest_id": self.second.pk}],
        ]
        for rules in rulesets:
            config = quiet_config(challenge_gates={"mode": "current", "rules": rules})
            with self.subTest(rules=rules), self.assertRaises(GateReferenceError), \
                    patch("apps.rpg.progression.engine.run_trial", side_effect=AssertionError("No trial")):
                simulate_progression(config, catalog=catalog)


    def test_repeatable_targets_are_refused_but_repeatable_predecessors_are_valid(self):
        QuestDefinition.objects.filter(pk=self.first.pk).update(is_repeatable=True)
        catalog = self.catalog()
        result = simulate_progression(self.config(), catalog=catalog)
        self.assertEqual(self.target(result, self.second)["completed_trials"], 1)
        bad = quiet_config(challenge_gates={"mode": "current", "rules": [{"quest_id": self.first.pk}]})
        with self.assertRaisesMessage(GateReferenceError, "one-off"):
            simulate_progression(bad, catalog=catalog)

    def test_late_predecessor_offering_cannot_fit_a_closed_successor_offering(self):
        config = self.config()
        config["challenge_gates"]["rules"][0]["available_until"] = "2026-01-10"
        config["challenge_gates"]["rules"].append({"quest_id": self.first.pk, "available_from": "2026-02-01"})
        result = simulate_progression(config, catalog=self.catalog())
        self.assertFalse(self.target(result, self.second)["reachable"])
        self.assertEqual(result["challenge_gates"]["gate_unreachable_finite_total"], 1)

    def test_missed_predecessor_native_deadline_blocks_child_instead_of_waiting_forever(self):
        QuestDefinition.objects.filter(pk=self.first.pk).update(target_value=2, duration_days=2)
        trial = Trial(self.config(), self.catalog(), 5)
        trial.day = 1
        trial.advance_challenges("reading_logged", {})
        # Sparse/unexpected attendance after an accepted promise can miss it;
        # the routine reachability calculation alone must not turn this into runway.
        trial.day = 4
        trial.challenge_gates.visit(trial)
        result = self.target(trial.report(), self.second)
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reasons"], ["prerequisite_window_expired"])
        self.assertFalse(result["temporarily_locked"])
        self.assertEqual(trial.challenge_gates.visits["waiting_for_gate"], 0)
        self.assertEqual(trial.challenge_gates.visits["exhausted_or_expired"], 1)

    def test_a_blocked_only_mount_path_cannot_bootstrap_its_own_expedition_loot(self):
        from apps.rpg.tests.test_progression_incubation import companion_catalog
        catalog = companion_catalog()
        cosmetic = N(pk=5, item_type="cosmetic_title", pet_species_id=None, potion_type_id=None,
                     rarity="common", coin_value=0, metadata={}, display_name="Expedition title", slug="title")
        items = {**catalog.items, 5: cosmetic}
        def quest(pk, trigger, rewards):
            return N(pk=pk, name=f"Path {pk}", required_badge_id=None, is_repeatable=False, quest_type="collection",
                     target_value=1, duration_days=30, trigger_filter={"allowed_triggers": [trigger]},
                     xp_reward=0, coin_reward=0, skill_tags=FrozenRows(),
                     reward_items=FrozenRows(N(item_id=item_id, quantity=4) for item_id in rewards))
        first, expedition = quest(1, "reading_logged", [1, 3, 4]), quest(2, "expedition_returned", [5])
        catalog = replace(catalog, skills=self.catalog().skills, items=items, quests=[first, expedition], badges=[],
                          pools={"expedition_returned": [N(item_id=5, item=cosmetic, min_level=0, weight=1)]})
        config = quiet_config(reading_minutes=10, expeditions_per_day=1, challenge_gates={"mode": "milestones",
            "rules": [{"quest_id": 1, "skill_id": self.unearned_skill.pk, "skill_level": 1}]})
        result = simulate_progression(config, catalog=catalog)
        self.assertFalse(self.target(result, first)["reachable"])
        self.assertFalse(self.target(result, expedition)["reachable"])
        self.assertGreater(result["challenge_gates"]["native_finite_total"], 0)
        self.assertEqual(result["challenge_gates"]["gate_reachable_finite_total"], 0)
        self.assertEqual(result["summary"]["mounts_p50"], 0)


    def test_definitely_expired_native_chapter_badge_is_blocked_not_waiting(self):
        badge = Badge.objects.create(name="Chapter seal", criteria_type="quest_completed",
            criteria_value={"quest_name": self.first.name}, award_coins=False, xp_bonus=0)
        QuestDefinition.objects.filter(pk=self.first.pk).update(target_value=2, duration_days=2)
        QuestDefinition.objects.filter(pk=self.second.pk).update(required_badge=badge)
        trial = Trial(quiet_config(reading_minutes=10), load_catalog(), 5)
        trial.day = 1
        trial.advance_challenges("reading_logged", {})
        trial.day = 4
        trial.challenge_gates.visit(trial)
        row = self.target(trial.report(), self.second)
        self.assertTrue(row["blocked"])
        self.assertEqual(row["blocked_reasons"], ["native_badge_prerequisite_expired"])
        self.assertFalse(row["temporarily_locked"])
        self.assertEqual(trial.challenge_gates.visits["waiting_for_gate"], 0)

    def test_viable_alternative_to_expired_native_badge_chapter_remains_waiting(self):
        for repeatable in (False, True):
            with self.subTest(repeatable=repeatable):
                alternate = QuestDefinition.objects.create(name=f"Alternate {repeatable}", quest_type="collection",
                    target_value=2, duration_days=30, is_repeatable=repeatable, is_system=True, coin_reward=0,
                    xp_reward=0, trigger_filter={"allowed_triggers": ["reading_logged"]})
                badge = Badge.objects.create(name=f"Alternative seal {repeatable}", criteria_type="quest_completed",
                    criteria_value={"quest_names": [self.first.name, alternate.name], "count": 1},
                    award_coins=False, xp_bonus=0)
                QuestDefinition.objects.filter(pk=self.first.pk).update(target_value=2, duration_days=2)
                QuestDefinition.objects.filter(pk=self.second.pk).update(required_badge=badge)
                trial = Trial(quiet_config(reading_minutes=10), load_catalog(), 5)
                trial.day = 1
                trial.advance_challenges("reading_logged", {})
                trial.day = 4
                row = self.target(trial.report(), self.second)
                self.assertFalse(row["blocked"])
                self.assertTrue(row["temporarily_locked"])
                alternate.delete()
                badge.delete()


    def test_gated_expedition_reachability_preserves_the_native_coin_commitment_filter(self):
        from apps.rpg.tests.test_progression_incubation import companion_catalog
        catalog = companion_catalog()
        items = {pk: N(**vars(item), slug=f"companion-item-{pk}") for pk, item in catalog.items.items()}
        title = N(pk=6, item_type="cosmetic_title", pet_species_id=None, potion_type_id=None,
                  rarity="common", coin_value=500, metadata={}, display_name="Costly title", slug="costly-title")
        items[6] = title
        badge = N(pk=9, name="Costly title collector", criteria_type="cosmetic_set_owned",
                  criteria_value={"slugs": [title.slug]}, rarity="common", xp_bonus=0, award_coins=False)
        def quest(pk, trigger, rewards, required_badge_id=None):
            return N(pk=pk, name=f"Commitment path {pk}", required_badge_id=required_badge_id,
                     is_repeatable=False, quest_type="collection", target_value=1, duration_days=30,
                     trigger_filter={"allowed_triggers": [trigger]}, xp_reward=0, coin_reward=0,
                     skill_tags=FrozenRows(), reward_items=FrozenRows(N(item_id=item_id, quantity=4) for item_id in rewards))
        mount_path = quest(1, "reading_logged", [1, 3, 4])
        authored_title_path = quest(2, "reading_logged", [6])
        title_badge_path = quest(3, "expedition_returned", [], required_badge_id=badge.pk)
        catalog = replace(catalog, skills=self.catalog().skills, items=items, badges=[badge],
                          quests=[mount_path, authored_title_path, title_badge_path],
                          pools={"expedition_returned": [N(item_id=6, item=title, min_level=0, weight=1)]})
        # Movement evaluates all native badge criteria, making this genuine
        # cosmetic-set gate reachable through the ungated authored reward.
        config = quiet_config(reading_minutes=10, movement_sessions_per_day=1, expeditions_per_day=1,
            reward_commitment={"enabled": True}, challenge_gates={"mode": "milestones", "rules": [
                {"quest_id": 2, "skill_id": self.unearned_skill.pk, "skill_level": 1}]})
        trial = Trial(config, catalog, 5)
        self.assertIn("quest:3", trial.finite_keys)
        self.assertFalse(trial.reward_commitment.allows(title, tier=config["expedition_tier"]))
        self.assertFalse(self.target(trial.report(), title_badge_path)["reachable"])
        result = simulate_progression(config, catalog=catalog)
        self.assertFalse(self.target(result, title_badge_path)["reachable"])
        self.assertGreaterEqual(result["challenge_gates"]["gate_unreachable_finite_total"], 4)
        self.assertEqual(result["challenge_gates"]["visits"]["waiting_for_gate_p50"], 0)
        self.assertEqual(self.target(result, title_badge_path)["completed_trials"], 0)
        # Exact long-expedition liability boundary remains reachable. This is
        # a policy filter, not a blanket removal of expedition cosmetics.
        permitted = N(**{**vars(title), "coin_value": trial.reward_commitment.static_limit(config["expedition_tier"])})
        allowed_catalog = replace(catalog, items={**items, 6: permitted}, pools={"expedition_returned": [
            N(item_id=6, item=permitted, min_level=0, weight=1)]})
        allowed = Trial(config, allowed_catalog, 5)
        self.assertTrue(self.target(allowed.report(), title_badge_path)["reachable"])
        installed = Trial({**config, "reward_commitment": {"enabled": False}}, catalog, 5)
        self.assertTrue(self.target(installed.report(), title_badge_path)["reachable"])

    def test_normalized_defaults_are_independent_and_bound_to_rule_fingerprint(self):
        from apps.rpg.progression import challenge_gates
        from apps.rpg.progression.engine import rules_fingerprint
        first, second = normalize_config(), normalize_config()
        first["challenge_gates"]["rules"].append({"quest_id": self.first.pk})
        self.assertEqual(second["challenge_gates"]["rules"], [])
        before = rules_fingerprint()
        with patch.object(challenge_gates, "ASSUMPTIONS", ["Changed interpretation"]):
            self.assertNotEqual(rules_fingerprint(), before)
