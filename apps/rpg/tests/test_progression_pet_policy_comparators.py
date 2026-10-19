"""Coin and expedition comparators share the run's immutable care policy."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.rpg.progression import engine
from apps.rpg.tests.test_progression_economy import quiet_config
from apps.rpg.tests.test_progression_incubation import companion_catalog


@override_settings(PET_INCUBATION_DURATION_SECONDS=86400)
class ProgressionPetPolicyComparatorTests(SimpleTestCase):
    def test_both_finite_comparators_retain_the_captured_policy_when_settings_change(self):
        policy = engine.pet_incubation_policy()
        actual_finite_keys = engine.Trial._finite_keys
        captured = []

        def capture(trial):
            captured.append((trial.config, trial.pet_incubation_policy))
            return actual_finite_keys(trial)

        with override_settings(PET_INCUBATION_DURATION_SECONDS=60), patch.object(
            engine.Trial, "_finite_keys", capture
        ):
            trial = engine.Trial(quiet_config(
                reward_commitment={"enabled": True},
                expedition_budget={"daily_launches": 2, "daily_items": 3},
            ), companion_catalog(), 42, incubation_policy=policy)

        self.assertEqual(len(captured), 3)
        self.assertTrue(all(snapshot is policy for _, snapshot in captured))
        parent, installed, unlimited = [config for config, _ in captured]
        self.assertFalse(installed["reward_commitment"]["enabled"])
        self.assertEqual(installed["expedition_budget"], parent["expedition_budget"])
        self.assertEqual(unlimited["reward_commitment"], parent["reward_commitment"])
        self.assertEqual(unlimited["expedition_budget"], {"daily_launches": None, "daily_items": None})
        self.assertIs(trial.pet_incubation_policy, policy)

    def test_combined_simulation_binds_all_trials_and_comparators_to_one_snapshot(self):
        policy = engine.pet_incubation_policy()
        actual_finite_keys = engine.Trial._finite_keys
        captured = []

        def capture(trial):
            captured.append(trial.pet_incubation_policy)
            return actual_finite_keys(trial)

        with override_settings(PET_INCUBATION_DURATION_SECONDS=60), patch.object(
            engine.Trial, "_finite_keys", capture
        ):
            report = engine.simulate_progression(quiet_config(
                trials=2,
                reward_commitment={"enabled": True},
                expedition_budget={"daily_launches": 3, "daily_items": None},
            ), catalog=companion_catalog(), incubation_policy=policy)

        self.assertEqual(len(captured), 6)
        self.assertTrue(all(snapshot is policy for snapshot in captured))
        self.assertEqual(report["pet_incubation_policy"]["duration_seconds"], 86400)
        self.assertEqual(report["rules_fingerprint"], engine.rules_fingerprint(incubation_policy=policy))
        self.assertEqual(report["engine_version"], "2026-10-18.5")
