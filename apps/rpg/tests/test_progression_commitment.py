"""New reward promises are bounded before grant; existing promises pay fully."""
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.rpg.content.loader import ContentPack
from apps.rpg.progression.catalog import Catalog, load_catalog
from apps.rpg.progression.engine import Trial, normalize_config, run_trial, simulate_progression
from apps.rpg.tests.test_progression_economy import empty_catalog, quiet_config


def config(**changes):
    return quiet_config(reward_commitment={"enabled": True}, **changes)


def item(pk, *, kind="food", coins=0, rarity="common"):
    return SimpleNamespace(pk=pk, item_type=kind, coin_value=coins,
                           metadata={"coins": coins} if kind == "coin_pouch" else {},
                           rarity=rarity, display_name=f"Item {pk}", slug=f"item-{pk}",
                           pet_species_id=None, potion_type_id=None, food_species_id=None)


def catalog_with(*items, trigger="chore_complete"):
    entries = [SimpleNamespace(pk=i, item_id=value.pk, item=value, weight=1, min_level=0)
               for i, value in enumerate(items, 1)]
    return Catalog({}, {value.pk: value for value in items}, {trigger: entries}, {}, [], [], {}, "synthetic")


def with_mounts(trial, count):
    trial.pets = {(pk, 1): SimpleNamespace(evolved_to_mount=True,
                                         growth_points=100,
                                         species=SimpleNamespace(name=f"Mount {pk}"))
                  for pk in range(1, count + 1)}
    return trial


def with_renewable_mount_source(catalog):
    """Give comparator tests a physical mount path outside expedition limits."""
    species = SimpleNamespace(pk=101, slug="synthetic-species", name="Synthetic companion", food_preference="")
    potion = SimpleNamespace(pk=102, slug="base")
    egg = item(1001, kind="egg")
    egg.pet_species_id = species.pk
    ingredient = item(1002, kind="potion")
    ingredient.potion_type_id = potion.pk
    food = item(1003)
    entries = [SimpleNamespace(pk=value.pk, trigger_type="chore_complete", item_id=value.pk,
                               item=value, weight=1, min_level=0) for value in (egg, ingredient, food)]
    return Catalog(dict(catalog.skills), {**catalog.items, **{value.pk: value for value in (egg, ingredient, food)}},
                   {**catalog.pools, "chore_complete": [*catalog.pools.get("chore_complete", []), *entries]},
                   {(species.pk, potion.pk): (species, potion)}, list(catalog.badges), list(catalog.quests),
                   dict(catalog.excluded_badges), "synthetic-with-mount")


class ProgressionCommitmentTests(SimpleTestCase):
    def test_configuration_is_opt_in_detached_and_incompatible_with_income_omission(self):
        self.assertEqual(normalize_config()["reward_commitment"], {"enabled": False})
        supplied = {"reward_commitment": {}}
        before = deepcopy(supplied)
        self.assertEqual(normalize_config(supplied)["reward_commitment"], {"enabled": False})
        self.assertEqual(supplied, before)
        with patch("apps.rpg.progression.engine.load_catalog", side_effect=AssertionError("No catalog read")):
            for value in (None, [], True, {"enabled": 1}, {"enabled": "true"}, {"daily_coins": 100}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    simulate_progression({"reward_commitment": value})
            with self.assertRaises(ValueError):
                simulate_progression(config(reward_budget={"daily_coins": 100}))

    def test_all_mounts_share_new_expedition_commitments_and_zero_coin_trips_remain_visible(self):
        trial = with_mounts(Trial(config(expeditions_per_day=15), empty_catalog(), 42), 15)
        trial.day = 1
        trial.launch_expeditions()
        self.assertEqual([row["coins"] for row in trial.pending_expeditions], [50, 25] + [0] * 13)
        report = trial.report()["reward_commitment"]
        self.assertEqual(report["summary"]["expedition_direct_committed"], 75)
        self.assertEqual(report["summary"]["zero_coin_launches"], 13)
        self.assertEqual(report["summary"]["empty_expedition_launches"], 13)
        self.assertEqual(report["summary"]["outstanding_direct_coins"], 75)
        self.assertEqual(trial.coins, 0)

    def test_activity_pouches_filter_full_values_before_selection_and_never_open_partially(self):
        catalog = catalog_with(item(1, kind="coin_pouch", coins=15), item(2, kind="coin_pouch", coins=50))
        trial = Trial(config(), catalog, 42)
        trial.day = 1
        with patch.object(trial.rng, "random", return_value=0):
            trial.drop("chore_complete")
            trial.drop("chore_complete")
        self.assertEqual(trial.inventory, {1: 1})
        trial.feed_and_hatch()
        self.assertEqual(trial.coins, 15)
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["activity_pouch_committed"], 15)
        self.assertEqual(summary["activity_empty_drops"], 1)
        self.assertEqual(summary["outstanding_pouch_coins"], 0)
        self.assertEqual(trial.inventory[1], 0)

    def test_eligible_tiers_are_reweighted_after_unaffordable_candidates_are_removed(self):
        catalog = catalog_with(item(1), item(2, kind="coin_pouch", coins=500, rarity="legendary"))
        trial = Trial(config(), catalog, 42)
        entries, weights = trial.eligible_pool("chore_complete")
        self.assertEqual([entry.item_id for entry in entries], [1])
        self.assertEqual(weights, [60])

    def test_every_installed_pouch_face_value_remains_whole_or_unavailable(self):
        for value in (5, 10, 15, 50, 100, 250, 500):
            with self.subTest(value=value):
                trial = Trial(config(), catalog_with(item(1, kind="coin_pouch", coins=value)), 42)
                trial.day = 1
                with patch.object(trial.rng, "random", return_value=0):
                    for _ in range(6):
                        trial.drop("chore_complete")
                expected_count = 25 // value
                self.assertEqual(trial.inventory[1], expected_count)
                trial.feed_and_hatch()
                self.assertEqual(trial.coins, expected_count * value)
                self.assertEqual(trial.report()["reward_commitment"]["summary"]["activity_pouch_committed"], expected_count * value)

    def test_expedition_reserves_direct_pouches_and_unowned_cosmetic_salvage_before_launch(self):
        catalog = catalog_with(item(1, kind="cosmetic_frame", coins=25), trigger="expedition_returned")
        trial = with_mounts(Trial(config(expeditions_per_day=1), catalog, 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        self.assertEqual(trial.pending_expeditions[0]["items"], [1])
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["committed_coins"], 75)
        self.assertEqual(summary["expedition_salvage_reserved"], 25)
        self.assertEqual(summary["contingent_salvage_coins"], 25)
        self.assertEqual(summary["empty_item_slots"], 2)
        # Another source can grant this cosmetic while the frozen trip is out.
        trial.grant_item(1, 1, "challenges")
        trial.day = 8
        trial.claim_expeditions()
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["expedition_direct_paid"], 50)
        self.assertEqual(summary["expedition_salvage_paid"], 25)
        self.assertEqual(summary["contingent_salvage_coins"], 0)
        self.assertEqual(summary["released_salvage_reserve"], 0)

    def test_unused_contingent_salvage_is_released_without_retroactive_budget_reuse(self):
        catalog = catalog_with(item(1, kind="cosmetic_frame", coins=25), trigger="expedition_returned")
        trial = with_mounts(Trial(config(expeditions_per_day=1), catalog, 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        trial.day = 2
        trial.claim_expeditions()
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["released_salvage_reserve"], 25)
        self.assertEqual(summary["expedition_salvage_paid"], 0)
        self.assertEqual(summary["committed_coins"], 75)
        self.assertEqual(trial.inventory[1], 1)

    def test_late_frozen_claims_and_owned_and_authored_pouches_pay_in_full(self):
        pouch = item(1, kind="coin_pouch", coins=500)
        trial = Trial(config(), catalog_with(pouch), 42)
        trial.day = 1
        trial.inventory[1] = 1  # An existing promise, with unknown historical origin.
        trial.grant_item(1, 1, "challenges")
        trial.pending_expeditions = [{"returns": 1, "coins": 200, "items": []}]
        trial.claim_expeditions()
        trial.feed_and_hatch()
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["pouch_coins_paid"], 1000)
        self.assertEqual(summary["authored_pouch_coins_granted"], 500)
        self.assertEqual(summary["expedition_direct_paid"], 200)
        self.assertEqual(summary["committed_coins"], 0)
        self.assertGreater(trial.coins, 100)

    def test_expedition_pouches_are_reserved_once_then_paid_fully(self):
        catalog = catalog_with(item(1, kind="coin_pouch", coins=10), trigger="expedition_returned")
        trial = with_mounts(Trial(config(expeditions_per_day=1), catalog, 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["committed_coins"], 70)
        self.assertEqual(summary["outstanding_pouch_coins"], 20)
        trial.day = 2
        trial.claim_expeditions()
        trial.feed_and_hatch()
        summary = trial.report()["reward_commitment"]["summary"]
        self.assertEqual(summary["committed_coins"], 70)
        self.assertEqual(summary["pouch_coins_paid"], 20)
        self.assertEqual(summary["outstanding_pouch_coins"], 0)

    def test_unaffordable_expedition_cosmetic_is_unavailable_content_not_extra_runway(self):
        catalog = with_renewable_mount_source(catalog_with(item(1, kind="cosmetic_frame", coins=50), trigger="expedition_returned"))
        trial = Trial(config(chores_per_day=1, expeditions_per_day=1), catalog, 42)
        self.assertNotIn("cosmetic:1", trial.finite_keys)
        policy = trial.report()["reward_commitment"]
        self.assertEqual(policy["installed_finite_total"], 4)  # Three companion stages plus the cosmetic.
        self.assertEqual(policy["unavailable_finite_total"], 1)
        self.assertEqual(policy["removed_finite_targets"], {"cosmetic": 1})
        self.assertEqual(policy["affected_paths"][0]["maximum_available_coins"], 25)

    def test_expensive_expedition_item_can_remain_reachable_through_an_activity_source(self):
        catalog = catalog_with(item(1, kind="cosmetic_frame", coins=50), trigger="expedition_returned")
        catalog = Catalog({}, dict(catalog.items), {**catalog.pools, "chore_complete": catalog.pools["expedition_returned"]},
                          {}, [], [], {}, "synthetic")
        catalog = with_renewable_mount_source(catalog)
        trial = Trial(config(chores_per_day=1, expeditions_per_day=1), catalog, 42)
        self.assertIn("cosmetic:1", trial.finite_keys)
        policy = trial.report()["reward_commitment"]
        self.assertEqual(policy["unavailable_finite_total"], 0)
        self.assertEqual([row["source"] for row in policy["affected_paths"]], ["expedition_returned"])

    def test_allocation_resets_per_calendar_day_without_carryover(self):
        trial = with_mounts(Trial(config(expeditions_per_day=1), empty_catalog(), 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        trial.day = 8
        trial.claim_expeditions()
        trial.launch_expeditions()
        self.assertEqual(trial.report()["reward_commitment"]["summary"]["expedition_direct_committed"], 100)
        self.assertEqual(trial.pending_expeditions[0]["coins"], 50)


class ProgressionCommitmentCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_disabled_policy_preserves_seeded_installed_progression_and_existing_income_experiment(self):
        catalog = load_catalog()
        for cap in (None, 100):
            routine = quiet_config(chores_per_day=2, project_minutes=20, expeditions_per_day=3,
                                   reward_budget={"daily_coins": cap})
            baseline = run_trial(routine, catalog, 42)
            explicit = run_trial({**routine, "reward_commitment": {"enabled": False}}, catalog, 42)
            self.assertEqual(baseline, explicit)
            self.assertEqual(explicit["reward_commitment"], {"enabled": False})

    def test_earned_only_items_remain_in_catalog_but_never_enter_random_drop_pools(self):
        from apps.rpg.models import ItemDefinition

        food = ItemDefinition.objects.get(slug="food-birdseed")
        self.assertTrue(any(entry.item_id == food.pk for pool in load_catalog().pools.values() for entry in pool))
        food.metadata = {**food.metadata, "no_random_drop": True}
        food.save(update_fields=["metadata"])
        after = load_catalog()
        self.assertIn(food.pk, after.items)
        self.assertFalse(any(entry.item_id == food.pk for pool in after.pools.values() for entry in pool))

    def test_candidate_is_seeded_detached_and_never_calls_live_award_writers(self):
        catalog = load_catalog()
        scenario = config(chores_per_day=2, project_minutes=20, expeditions_per_day=3, trials=2)

        def forbid_sql(execute, sql, params, many, context):
            self.fail(f"Commitment simulation touched SQL: {sql[:100]}")

        with connection.execute_wrapper(forbid_sql), \
                patch("apps.rewards.services.CoinService.award_coins", side_effect=AssertionError("Live award")), \
                patch("apps.rpg.services.InventoryItemService.open_coin_pouch", side_effect=AssertionError("Live pouch")):
            first = simulate_progression(scenario, catalog=catalog)
            second = simulate_progression(scenario, catalog=catalog)
        self.assertEqual(first, second)
        policy = first["reward_commitment"]
        self.assertTrue(policy["enabled"])
        summary = policy["summary"]
        self.assertEqual(summary["committed_coins"]["mean"], sum(summary[key]["mean"] for key in (
            "expedition_direct_committed", "expedition_pouch_committed", "expedition_salvage_reserved", "activity_pouch_committed")))
        self.assertEqual(summary["expedition_direct_committed"]["mean"],
                         summary["expedition_direct_paid"]["mean"] + summary["outstanding_direct_coins"]["mean"])
        self.assertEqual(summary["expedition_salvage_reserved"]["mean"], sum(summary[key]["mean"] for key in (
            "expedition_salvage_paid", "released_salvage_reserve", "contingent_salvage_coins")))
        sources = {row["source"]: row for row in policy["pouch_sources"]}
        self.assertEqual(summary["activity_pouch_committed"]["mean"], sources["activity_random"]["granted_coins"]["mean"])
        self.assertEqual(summary["expedition_pouch_committed"]["mean"],
                         sources["expeditions"]["granted_coins"]["mean"] + sources["expeditions"]["pending_coins"]["mean"])
        for row in sources.values():
            self.assertEqual(row["granted_coins"]["mean"] + row["pending_coins"]["mean"],
                             row["opened_coins"]["mean"] + row["outstanding_coins"]["mean"])
        self.assertEqual(summary["pouch_coins_paid"]["mean"], sum(row["opened_coins"]["mean"] for row in sources.values()))
        self.assertEqual(summary["outstanding_pouch_coins"]["mean"], sum(row["outstanding_coins"]["mean"] for row in sources.values()))
        for row in first["trace"]:
            self.assertLessEqual(row["reward_commitment_expedition_today_p90"], 75)
            self.assertLessEqual(row["reward_commitment_activity_pouch_today_p90"], 25)


class ProgressionQuestBoundaryTests(TestCase):
    def test_one_fact_cannot_also_progress_a_quest_unlocked_by_its_own_completion(self):
        from apps.achievements.models import Badge, UserBadge
        from apps.quests.goals import ingest_activity
        from apps.quests.models import ChallengeGoal, QuestDefinition
        from config.tests.factories import make_family

        child = make_family(children=[{"username": "chapter-boundary"}]).children[0]
        first = QuestDefinition.objects.create(name="First chapter", quest_type="collection", target_value=1,
                                               duration_days=7, is_system=True, coin_reward=0, xp_reward=0,
                                               trigger_filter={"allowed_triggers": ["habit_log"]})
        gate = Badge.objects.create(name="First chapter seal", criteria_type="quest_completed",
                                    criteria_value={"quest_name": first.name}, award_coins=False, xp_bonus=0)
        second = QuestDefinition.objects.create(name="Second chapter", quest_type="collection", target_value=1,
                                                duration_days=7, is_system=True, coin_reward=0, xp_reward=0,
                                                required_badge=gate,
                                                trigger_filter={"allowed_triggers": ["habit_log"]})
        trial = Trial(quiet_config(habits_per_day=1), load_catalog(), 42)
        for day in (1, 2):
            at = timezone.now() + timedelta(days=day)
            with patch("django.utils.timezone.now", return_value=at):
                ingest_activity(child, "habit_log", f"chapter-{day}", "habit_log", occurred_at=at)
            trial.day = day
            trial.event("habit_log", drops=False)
            self.assertTrue(UserBadge.objects.filter(user=child, badge=gate).exists())
            if day == 1:
                self.assertFalse(ChallengeGoal.objects.filter(user=child, catalog_definition=second).exists())
                self.assertNotIn(second.pk, trial.completed_quests)
                self.assertNotIn(second.pk, trial.quest_windows)
            else:
                self.assertTrue(ChallengeGoal.objects.filter(user=child, catalog_definition=second).exists())
                self.assertIn(second.pk, trial.completed_quests)
