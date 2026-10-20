"""Additional collectible colors cannot multiply one species's daily trips."""
from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.rpg.progression.engine import SimPet, Trial
from apps.rpg.progression.catalog import FrozenRows
from apps.rpg.tests.test_progression_economy import quiet_config
from apps.rpg.tests.test_progression_incubation import companion_catalog


def elemental_catalog():
    catalog = companion_catalog()
    species, base = catalog.pairs[(1, 1)]
    fire, ice = N(pk=2, slug="fire", name="Fire"), N(pk=3, slug="ice", name="Ice")
    items = dict(catalog.items)
    items[1] = N(**{**vars(items[1]), "coin_value": 7})
    items[3] = N(**{**vars(items[3]), "potion_type": base})
    for pk, potion in ((5, fire), (6, ice)):
        items[pk] = N(pk=pk, item_type="potion", potion_type_id=potion.pk, potion_type=potion,
                      pet_species_id=None, rarity="uncommon", metadata={}, coin_value=0,
                      display_name=potion.name, slug=f"{potion.slug}-potion")
    pairs = {**catalog.pairs, (1, 2): (species, fire), (1, 3): (species, ice)}
    return replace(catalog, items=items, pairs=pairs)


class SpeciesExpeditionProjectionTests(SimpleTestCase):
    def trial(self, **changes):
        catalog = elemental_catalog()
        trial = Trial(quiet_config(expeditions_per_day=15, **changes), catalog, 42)
        trial.day = 1
        for pair, (species, potion) in catalog.pairs.items():
            trial.pets[pair] = SimPet(species, potion, 100, True)
        return trial

    def test_four_variants_across_two_species_launch_only_two_trips(self):
        trial = self.trial()
        trial.launch_expeditions()
        self.assertEqual(len(trial.pending_expeditions), 2)
        self.assertEqual([e["pair"] for e in trial.pending_expeditions], [(1, 1), (2, 1)])

    def test_collecting_does_not_rearm_species_same_day_but_next_day_does(self):
        trial = self.trial()
        trial.launch_expeditions()
        for expedition in trial.pending_expeditions:
            expedition["returns"] = 1
        trial.claim_expeditions()
        self.assertFalse(trial.pending_expeditions)
        trial.launch_expeditions()
        self.assertEqual(trial.pending_expeditions, [])
        trial.day = 2
        trial.launch_expeditions()
        self.assertEqual(len(trial.pending_expeditions), 2)

    def test_pending_other_appearance_blocks_next_day_until_claim(self):
        trial = self.trial()
        trial.pending_expeditions = [{"pair": (1, 3), "returns": 3, "coins": 15, "items": []}]
        trial.day = 2
        trial.launch_expeditions()
        self.assertEqual([e["pair"] for e in trial.pending_expeditions], [(1, 3), (2, 1)])

    def test_native_species_limit_runs_before_hypothetical_global_quota(self):
        trial = self.trial(expedition_budget={"daily_launches": 1, "daily_items": 0})
        with patch.object(trial.rng, "random", wraps=trial.rng.random) as draws:
            trial.launch_expeditions()
        self.assertEqual(draws.call_count, 1)
        self.assertEqual([e["pair"] for e in trial.pending_expeditions], [(1, 1)])
        totals = trial.expedition_budget.totals
        self.assertEqual((totals["eligible_trips"], totals["launched_trips"], totals["prevented_trips"]), (2, 1, 1))

    def test_mount_insertion_order_cannot_change_selected_color(self):
        trial = self.trial()
        trial.pets = dict(reversed(tuple(trial.pets.items())))
        trial.launch_expeditions()
        self.assertEqual([e["pair"] for e in trial.pending_expeditions], [(1, 1), (2, 1)])

    def test_preferred_food_feeds_oldest_unevolved_appearance_and_keeps_growth_rules(self):
        catalog = elemental_catalog()
        food = N(**{**vars(catalog.items[4]), "food_species_id": 1})
        trial = Trial(quiet_config(), replace(catalog, items={**catalog.items, 4: food}), 42)
        species, fire = catalog.pairs[(1, 2)]
        trial.pets[(1, 2)] = SimPet(species, fire)
        trial.pets[(1, 1)] = SimPet(*catalog.pairs[(1, 1)])
        trial.inventory[4] = 3
        trial.feed_and_hatch()
        self.assertEqual(trial.pets[(1, 2)].growth_points, 100)
        self.assertTrue(trial.pets[(1, 2)].evolved_to_mount)
        self.assertEqual(trial.pets[(1, 1)].growth_points, 0)
        self.assertEqual(trial.inventory[4], 0)


class ElementalChallengeProjectionTests(SimpleTestCase):
    def trial(self, *, rewards=(1, 5), owned=((1, 1),)):
        catalog = elemental_catalog()
        quest = N(pk=1, name="Ember Nest", required_badge_id=None, is_repeatable=False,
                  quest_type="collection", target_value=1, duration_days=180,
                  trigger_filter={"allowed_triggers": ["reading_logged"]}, coin_reward=0, xp_reward=0,
                  skill_tags=FrozenRows(),
                  reward_items=FrozenRows(N(item_id=pk, quantity=1) for pk in rewards))
        trial = Trial(quiet_config(reading_minutes=10), replace(catalog, quests=[quest]), 42)
        trial.day = 1
        for pair in owned:
            trial.pets[pair] = SimPet(*catalog.pairs[pair], 100, True)
        return trial

    def test_base_grown_keeps_bundle_egg_for_missing_elemental_pair(self):
        trial = self.trial()
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.inventory[1], 1)
        self.assertEqual(trial.inventory[5], 1)
        self.assertEqual(trial.source_totals["challenges_salvage"]["coins"], 0)
        trial.feed_and_hatch()
        self.assertEqual(trial.pending_incubation.pair, (1, 2))

    def test_exact_elemental_grown_salvages_egg_but_keeps_potion(self):
        trial = self.trial(owned=((1, 1), (1, 2)))
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.inventory[1], 0)
        self.assertEqual(trial.inventory[5], 1)
        self.assertEqual(trial.source_totals["challenges_salvage"]["coins"], 7)

    def test_egg_remains_when_one_of_multiple_promised_colors_is_missing(self):
        trial = self.trial(rewards=(1, 5, 6), owned=((1, 1), (1, 2)))
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.inventory[1], 1)
        self.assertEqual((trial.inventory[5], trial.inventory[6]), (1, 1))

    def test_base_bundle_keeps_existing_species_wide_salvage(self):
        trial = self.trial(rewards=(1, 3), owned=((1, 2),))
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.inventory[1], 0)
        self.assertEqual(trial.source_totals["challenges_salvage"]["coins"], 7)
