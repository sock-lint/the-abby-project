"""The installed Lab control shares new random rewards and retains old promises."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import PetSpecies, PotionType
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, rules_fingerprint
from apps.rpg.services import DropService, InventoryItemService
from apps.rpg.tests.test_progression_economy import quiet_config
from config.tests.factories import make_family


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionCoinRebalanceTests(TestCase):
    def setUp(self):
        self.child = make_family("Coin forecast", children=[{"username": "coin-forecast-child"}]).children[0]
        self.original = ItemDefinition.objects.create(
            slug="pouch-medium", name="Medium Coin Pouch", item_type="coin_pouch", rarity="uncommon",
            coin_value=15, metadata={"coins": 15},
        )
        self.replacement = ItemDefinition.objects.create(
            slug="pouch-medium-v2", name="Medium Coin Pouch", item_type="coin_pouch", rarity="uncommon",
            coin_value=3, metadata={"coins": 3, "no_random_drop": True},
        )
        self.entry = DropTable.objects.create(trigger_type="chore_complete", item=self.original, weight=7)
        # A macro can materialize the replacement too. It must not become a
        # second candidate that changes the chance of receiving a pouch.
        DropTable.objects.create(trigger_type="chore_complete", item=self.replacement, weight=7)

    def trial(self, **changes):
        trial = Trial(quiet_config(**changes), load_catalog(), 42)
        trial.day = 1
        return trial

    def test_new_random_pouch_matches_live_without_reading_or_writing_during_simulation(self):
        trial = self.trial()
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0):
            trial.drop("chore_complete")
            trial.feed_and_hatch()
        self.assertEqual(trial.coins, 3)
        self.assertEqual(trial.inventory[self.original.pk], 0)
        self.assertEqual(trial.sink_totals["coin_pouch_opening"]["items"], 1)

        with patch("apps.rpg.services.random.random", return_value=0):
            dropped = DropService.process_drops(self.child, "chore_complete")
        self.assertEqual(dropped[0]["item_id"], self.replacement.pk)
        opened = InventoryItemService.open_coin_pouch(self.child, self.replacement.pk)
        self.assertEqual(trial.coins, opened["coins_awarded"])
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_random_selection_retains_source_odds_and_has_no_duplicate_replacement(self):
        other = ItemDefinition.objects.create(slug="ordinary-food", name="Food", item_type="food", rarity="uncommon")
        other_entry = DropTable.objects.create(trigger_type="chore_complete", item=other, weight=13)
        trial = self.trial()
        def choose_original(entries, **kwargs):
            return [next(entry for entry in entries if entry.item_id == self.original.pk)]
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0), \
                patch.object(trial.rng, "choices", side_effect=choose_original) as lab_draw:
            trial.drop("chore_complete")
        with patch("apps.rpg.services.random.random", return_value=0), \
                patch("apps.rpg.services.random.choices", side_effect=choose_original) as live_draw:
            DropService.process_drops(self.child, "chore_complete")
        for draw in (lab_draw, live_draw):
            self.assertCountEqual([entry.pk for entry in draw.call_args.args[0]], [self.entry.pk, other_entry.pk])
        def selection_weights(draw):
            return {entry.pk: weight for entry, weight in zip(draw.call_args.args[0], draw.call_args.kwargs["weights"])}
        self.assertEqual(selection_weights(lab_draw), selection_weights(live_draw))
        self.assertEqual(trial.inventory[self.replacement.pk], 1)

    def test_new_expedition_has_live_payout_and_new_pouch_but_legacy_trip_pays_in_full(self):
        species = PetSpecies.objects.create(slug="forecast-bird", name="Bird")
        potion = PotionType.objects.create(slug="forecast-base", name="Base")
        trial = self.trial(expeditions_per_day=1)
        trial.pets[(species.pk, potion.pk)] = SimpleNamespace(
            species=SimpleNamespace(name="Bird"), evolved_to_mount=True, growth_points=100,
        )
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0.5):
            trial.launch_expeditions()
        with patch("apps.pets.expeditions.random.random", return_value=0.5):
            live_loot = ExpeditionService._roll_loot(self.child, "long")
        new_trip = trial.pending_expeditions[0]
        self.assertEqual(new_trip["coins"], 15)
        self.assertEqual(new_trip["coins"], live_loot["coins"])
        self.assertEqual(new_trip["items"], [self.replacement.pk] * 3)
        self.assertEqual(new_trip["items"], [row["item_id"] for row in live_loot["items"]])
        trial.pending_expeditions = [{"pair": (species.pk, potion.pk), "returns": 1, "coins": 75,
                                      "items": [self.original.pk], "budget_promised_items": 1}]
        with self.assertNumQueries(0):
            trial.claim_expeditions()
            trial.feed_and_hatch()
        self.assertEqual(trial.source_totals["expeditions"]["coins"], 75)
        self.assertEqual(trial.source_totals["coin_pouches"]["coins"], 15)

    def test_owned_and_authored_pouches_redeem_in_full_with_new_random_pouches(self):
        trial = self.trial()
        trial.inventory[self.original.pk] = 1
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0):
            trial.grant_item(self.original.pk, 1, "challenges")
            trial.drop("chore_complete")
            trial.feed_and_hatch()
        self.assertEqual(trial.coins, 33)
        self.assertEqual(trial.sink_totals["coin_pouch_opening"]["items"], 3)

    def test_commitment_prototype_keeps_original_pouch_values_and_hypothetical_tiers(self):
        trial = self.trial(reward_commitment={"enabled": True}, expeditions_per_day=1)
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0):
            trial.drop("chore_complete")
        self.assertEqual(trial.inventory[self.original.pk], 1)
        self.assertEqual(trial.inventory[self.replacement.pk], 0)
        self.assertEqual(trial.reward_commitment.totals["activity_pouch_committed"], 15)
        trial.pets[(1, 1)] = SimpleNamespace(species=SimpleNamespace(name="Bird"),
                                            evolved_to_mount=True, growth_points=100)
        with self.assertNumQueries(0):
            trial.launch_expeditions()
        self.assertEqual(trial.pending_expeditions[0]["coins"], 50)

    def test_catalog_binds_replacement_values_and_capacity_uses_only_new_random_identity(self):
        trial = self.trial(chores_per_day=1)
        self.assertEqual(set(trial.catalog.items), {self.original.pk, self.replacement.pk})
        self.assertEqual([entry.item_id for entry in trial.catalog.pools["chore_complete"]], [self.original.pk])
        with self.assertNumQueries(0):
            self.assertEqual(trial._obtainable_drop_items("chore_complete"), {self.replacement.pk})
            self.assertEqual(trial._reachability_capacity.renewable, {self.replacement.pk})
        previous = trial.catalog.fingerprint
        self.replacement.metadata = {"coins": 4, "no_random_drop": True}
        self.replacement.save(update_fields=["metadata"])
        self.assertNotEqual(previous, load_catalog().fingerprint)
        # A saved forecast keeps its exact version even after catalog edits.
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0):
            trial.drop("chore_complete")
            trial.feed_and_hatch()
        self.assertEqual(trial.coins, 3)

    def test_rule_binding_tracks_mapping_and_face_value_policy_changes(self):
        from apps.rpg import coin_policy

        original = rules_fingerprint()
        with patch.dict(coin_policy.RANDOM_POUCH_REPLACEMENTS, {"pouch-medium": "pouch-medium-future"}):
            self.assertNotEqual(original, rules_fingerprint())
        with patch.dict(coin_policy.RANDOM_POUCH_VALUES, {"pouch-medium": (15, 4)}):
            self.assertNotEqual(original, rules_fingerprint())
