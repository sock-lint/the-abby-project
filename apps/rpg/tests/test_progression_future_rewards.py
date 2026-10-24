"""Installed forecasts use the same prospective earning limits as new awards."""
from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.rpg import coin_policy
from apps.rpg.progression.catalog import FrozenRows
from apps.rpg.progression.engine import SimPet, Trial, rules_fingerprint
from apps.rpg.tests.test_progression_economy import empty_catalog, quiet_config


class FutureRewardProjectionTests(SimpleTestCase):
    def trial(self, **changes):
        trial = Trial(quiet_config(**changes), empty_catalog(), 42)
        trial.day = 1
        return trial

    def test_installed_control_has_two_launches_across_all_species_and_repeated_calls(self):
        trial = self.trial(expeditions_per_day=15)
        for pk in range(1, 5):
            trial.pets[(pk, 1)] = SimPet(N(pk=pk, name=f"Species {pk}"), N(pk=1), 100, True)
        trial.launch_expeditions()
        self.assertEqual(len(trial.pending_expeditions), 2)
        trial.launch_expeditions()
        self.assertEqual(len(trial.pending_expeditions), 2)
        trial.day = 2
        trial.launch_expeditions()
        self.assertEqual(len(trial.pending_expeditions), 4)

    def test_new_ordinary_duplicate_is_smaller_but_saved_trip_keeps_original_value(self):
        frame = N(pk=1, item_type="cosmetic_frame", coin_value=150, display_name="Moonlit",
                  slug="test-moonlit", rarity="rare", metadata={})
        catalog = replace(empty_catalog(), items={1: frame})
        trial = Trial(quiet_config(), catalog, 42)
        trial.day = 1
        trial.inventory[1] = 1
        trial.grant_item(1, 1, "drops", salvage_cosmetic=True)
        self.assertEqual(trial.coins, 10)
        trial.pending_expeditions = [{"pair": (1, 1), "returns": 1, "coins": 75, "items": [1]}]
        trial.claim_expeditions()
        self.assertEqual(trial.source_totals["expeditions_salvage"]["coins"], 150)
        self.assertEqual(trial.source_totals["expeditions"]["coins"], 75)

    def test_distinct_day_challenge_cannot_complete_from_same_day_taps(self):
        quest = N(pk=1, name="A steady habit", required_badge_id=None, is_repeatable=True,
                  quest_type="collection", target_value=3, duration_days=7,
                  trigger_filter={"allowed_triggers": ["habit_log"],
                                  "distinct_active_days": True, "reward_policy_version": 2},
                  coin_reward=10, xp_reward=0, skill_tags=FrozenRows(), reward_items=FrozenRows())
        catalog = replace(empty_catalog(), quests=[quest])
        trial = Trial(quiet_config(habits_per_day=3), catalog, 42)
        trial.day = 1
        for _ in range(3):
            trial.advance_challenges("habit_log", {})
        self.assertEqual(trial.quest_windows[1]["progress"], 1)
        self.assertEqual(trial.source_totals["challenges"]["coins"], 0)
        for day in (2, 3):
            trial.day = day
            trial.advance_challenges("habit_log", {})
        self.assertEqual(trial.source_totals["challenges"]["coins"], 10)

    def test_rule_fingerprint_tracks_live_limit_values(self):
        before = rules_fingerprint()
        with patch.object(coin_policy, "EXPEDITION_DAILY_LIMIT", 3):
            self.assertNotEqual(before, rules_fingerprint())
        with patch.object(coin_policy, "RANDOM_COSMETIC_SALVAGE_LIMIT", 11):
            self.assertNotEqual(before, rules_fingerprint())

    def test_many_taps_cannot_make_a_five_day_goal_reachable_on_three_active_days(self):
        quest = N(pk=1, name="Five active days", required_badge_id=None, is_repeatable=False,
                  quest_type="collection", target_value=5, duration_days=7,
                  trigger_filter={"allowed_triggers": ["habit_log"],
                                  "distinct_active_days": True, "reward_policy_version": 2},
                  coin_reward=10, xp_reward=0, skill_tags=FrozenRows(), reward_items=FrozenRows())
        trial = Trial(quiet_config(habits_per_day=3, active_days_per_week=3),
                      replace(empty_catalog(), quests=[quest]), 42)
        self.assertEqual(trial._challenge_capacity(quest, {"habit_log"}), 3)
        self.assertNotIn(quest.pk, {q.pk for q in trial.quests})

    def test_new_trip_honors_saved_salvage_even_when_catalog_face_value_is_now_zero(self):
        frame = N(pk=1, item_type="cosmetic_frame", coin_value=0, display_name="Edited frame",
                  slug="edited-frame", rarity="rare", metadata={})
        trial = Trial(quiet_config(), replace(empty_catalog(), items={1: frame}), 42)
        trial.day = 1
        trial.inventory[1] = 1
        trial.pending_expeditions = [{"pair": (1, 1), "returns": 1, "coins": 15, "items": [1],
                                      "salvage_coin_values": {1: 10}}]
        trial.claim_expeditions()
        self.assertEqual(trial.source_totals["expeditions_salvage"]["coins"], 10)
        self.assertEqual(trial.inventory[1], 1)
