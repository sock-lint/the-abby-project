"""Incubation is an elapsed promise; visits explicitly claim, then care."""
from types import SimpleNamespace as N
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.rpg.progression.catalog import Catalog
from apps.rpg.progression import engine
from apps.rpg.tests.test_progression_economy import quiet_config


def companion_catalog():
    species = [N(pk=pk, slug=f"synthetic-{pk}", name=f"Bird {pk}", food_preference="seed") for pk in (1, 2)]
    potion = N(pk=1, slug="base", name="Base")
    items = {
        pk: N(pk=pk, item_type="egg", pet_species_id=pk, pet_species=bird, potion_type_id=None,
              rarity="common", metadata={}, coin_value=0, display_name=f"Bird {pk} egg")
        for pk, bird in enumerate(species, 1)
    }
    items[3] = N(pk=3, item_type="potion", potion_type_id=1, pet_species_id=None,
                 rarity="common", metadata={}, coin_value=0, display_name="Base potion")
    items[4] = N(pk=4, item_type="food", food_species_id=None, pet_species_id=None, potion_type_id=None,
                 rarity="common", metadata={"growth": 30}, coin_value=0, display_name="Food")
    badges = [N(pk=1, name="First hatch", criteria_type="pets_hatched", criteria_value={"count": 1},
                rarity="common", xp_bonus=0, award_coins=True),
              N(pk=2, name="First grown", criteria_type="mounts_evolved", criteria_value={"count": 1},
                rarity="common", xp_bonus=0, award_coins=True)]
    return Catalog({}, items, {}, {(bird.pk, 1): (bird, potion) for bird in species}, badges, [], {}, "synthetic-incubation")


@override_settings(PET_INCUBATION_DURATION_SECONDS=86400, COINS_PER_BADGE_RARITY={"common": 7})
class ProgressionIncubationTimingTests(SimpleTestCase):
    def trial(self, **changes):
        trial = engine.Trial(quiet_config(**changes), companion_catalog(), 42)
        trial.inventory.update({1: 1, 2: 1, 3: 2, 4: 4})
        return trial

    def test_start_reserves_only_one_pair_without_pet_food_growth_or_badge_awards(self):
        trial = self.trial()
        trial.daily(1)
        self.assertEqual(len(trial.pets), 0)
        self.assertFalse(trial.badges)
        self.assertFalse(trial.coins)
        self.assertEqual(dict(trial.inventory), {1: 0, 2: 1, 3: 1, 4: 4})
        self.assertNotIn("first_pet", trial.milestones)
        self.assertEqual((trial.trace[-1]["incubating_eggs"], trial.trace[-1]["ready_eggs"]), (1, 0))
        starts = [row for row in trial.events if row["source"] == "incubation_started"]
        self.assertEqual(len(starts), 1)
        self.assertEqual({key: starts[0][key] for key in ("day", "target", "duration_seconds", "ready_day")},
                         {"day": 1, "target": "Bird 1", "duration_seconds": 86400, "ready_day": 2})
        trial.feed_and_hatch()
        self.assertEqual(dict(trial.inventory), {1: 0, 2: 1, 3: 1, 4: 4})

    def test_claim_at_next_active_visit_precedes_activity_rewards_and_end_visit_feeding(self):
        trial = self.trial(reading_minutes=10)
        trial.daily(1)
        self.assertEqual(len(trial.pets), 0)
        trial.daily(2)
        self.assertEqual((len(trial.pets), len(trial.mounts)), (1, 1))
        self.assertEqual((trial.milestones["first_pet"], trial.milestones["first_mount"]), (2, 2))
        sources = [row["source"] for row in trial.events if row["day"] == 2]
        self.assertLess(sources.index("incubation_ready"), sources.index("hatch"))
        self.assertLess(sources.index("hatch"), sources.index("reading"))
        self.assertLess(sources.index("reading"), sources.index("evolution"))
        self.assertEqual(trial.badges, {1, 2})
        self.assertEqual(trial.source_totals["badges"]["coins"], 14)
        self.assertEqual(sum(row["source"] == "hatch" for row in trial.events), 1)
        self.assertEqual(sum(row["source"] == "incubation_started" for row in trial.events), 2)

    def test_inactive_days_mark_ready_once_without_claiming_feeding_or_paying(self):
        trial = self.trial(active_days_per_week=1)
        for day in range(1, 8):
            trial.daily(day)
        self.assertFalse(trial.pets)
        self.assertFalse(trial.badges)
        self.assertEqual(trial.inventory[4], 4)
        self.assertTrue(all((row["incubating_eggs"], row["ready_eggs"]) == (0, 1) for row in trial.trace[1:]))
        ready = [row for row in trial.events if row["source"] == "incubation_ready"]
        self.assertEqual([(row["day"], row["target"]) for row in ready], [(2, "Bird 1")])
        trial.daily(8)
        self.assertEqual(trial.milestones["first_pet"], 8)
        self.assertEqual(trial.source_totals["badges"]["coins"], 14)
        self.assertTrue(all(row["incubating_eggs"] + row["ready_eggs"] <= 1 for row in trial.trace))

    @override_settings(PET_INCUBATION_DURATION_SECONDS=86401)
    def test_a_full_elapsed_deadline_cannot_round_down_to_the_next_day(self):
        trial = self.trial()
        trial.daily(1)
        start = next(row for row in trial.events if row["source"] == "incubation_started")
        self.assertEqual(start["ready_day"], 3)
        trial.daily(2)
        self.assertFalse(trial.pets)
        self.assertEqual((trial.trace[-1]["incubating_eggs"], trial.trace[-1]["ready_eggs"]), (1, 0))
        self.assertFalse(any(row["source"] == "incubation_ready" for row in trial.events))
        trial.daily(3)
        self.assertEqual(trial.milestones["first_pet"], 3)

    def test_pending_deadline_and_trial_policy_survive_settings_changes(self):
        trial = self.trial(feed_strategy="none")
        trial.daily(1)
        self.assertFalse(trial.pets)
        with override_settings(PET_INCUBATION_DURATION_SECONDS=7 * 86400):
            trial.daily(2)
        self.assertEqual(trial.milestones["first_pet"], 2)
        starts = [row for row in trial.events if row["source"] == "incubation_started"]
        self.assertEqual([row["duration_seconds"] for row in starts], [86400, 86400])
        self.assertEqual([row["ready_day"] for row in starts], [2, 3])
        trial.daily(3)
        self.assertEqual(len(trial.pets), 2)
        self.assertEqual(sum(row["source"] == "hatch" for row in trial.events), 2)
        self.assertEqual(trial.source_totals["badges"]["coins"], 7)


@override_settings(PET_INCUBATION_DURATION_SECONDS=86400)
class ProgressionIncubationBindingTests(SimpleTestCase):
    def test_changed_elapsed_calendar_clock_invalidates_saved_rules(self):
        before = engine.rules_fingerprint()
        with patch.object(engine, "SECONDS_PER_DAY", 86401):
            self.assertNotEqual(before, engine.rules_fingerprint())

    def test_policy_snapshot_is_immutable_and_duration_changes_rules_binding(self):
        policy = engine.pet_incubation_policy()
        self.assertEqual(dict(policy), {"duration_seconds": 86400, "max_active": 1, "clock": "elapsed_seconds",
            "start_strategy": "first_compatible_pair_during_care", "claim_strategy": "next_active_care_visit_at_or_after_ready"})
        with self.assertRaises(TypeError):
            policy["duration_seconds"] = 1
        before = engine.rules_fingerprint(incubation_policy=policy)
        with override_settings(PET_INCUBATION_DURATION_SECONDS=60):
            self.assertNotEqual(engine.rules_fingerprint(), before)
            self.assertEqual(engine.rules_fingerprint(incubation_policy=policy), before)

    def test_one_run_threads_one_frozen_policy_to_all_trials_and_its_report(self):
        actual_run = engine.run_trial
        captured = []

        def changed_setting_run(config, catalog, seed, **kwargs):
            captured.append(kwargs["incubation_policy"])
            with override_settings(PET_INCUBATION_DURATION_SECONDS=60):
                return actual_run(config, catalog, seed, **kwargs)

        with patch.object(engine, "run_trial", side_effect=changed_setting_run):
            report = engine.simulate_progression(quiet_config(trials=2), catalog=companion_catalog())
        self.assertEqual(len(captured), 2)
        self.assertIs(captured[0], captured[1])
        self.assertEqual(report["pet_incubation_policy"]["duration_seconds"], 86400)
        self.assertEqual(report["rules_fingerprint"], engine.rules_fingerprint(incubation_policy=captured[0]))
        self.assertIn("incubating_eggs_p50", report["trace"][0])
        self.assertIn("ready_eggs_p90", report["trace"][0])
