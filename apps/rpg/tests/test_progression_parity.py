"""Independent checks against the live reward services and persisted catalog.

Forecast tests should catch a second, internally consistent reward engine that
quietly disagrees with the application. These comparisons therefore capture
real drop selections and exercise real pet/goal services on disposable records.
"""
from io import StringIO
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.chronicle.services import ChronicleService
from apps.pets.expeditions import ExpeditionService
from apps.movement.services import MovementSessionService
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.pets.services import PetService
from apps.quests.goals import ingest_activity
from apps.quests.models import ChallengeOccurrence, QuestDefinition, QuestSkillTag
from apps.rewards.services import CoinService
from apps.rpg.catalog_support import item_is_available
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import CharacterProfile, DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import load_catalog, snapshot_catalog
from apps.rpg.progression.engine import SimPet, Trial, audit_catalog, rules_fingerprint, run_trial
from apps.rpg.services import DropService
from apps.wellbeing.services import GRATITUDE_FIRST_OF_DAY_COINS
from config.tests.factories import make_family


CONFIG = {
    "horizon_days": 30,
    "trials": 2,
    "seed": 42,
    "active_days_per_week": 5,
    "reading_minutes": 10,
    "project_minutes": 0,
    "chores_per_day": 2,
    "chore_coins": 10,
    "chore_xp": 10,
    "habits_per_day": 1,
    "habit_xp": 5,
    "movement_sessions_per_day": 0,
    "movement_minutes": 20,
    "movement_intensity": "medium",
    "creations_per_day": 0,
    "journal_per_day": True,
    "feed_strategy": "feed_all",
    "expeditions_per_day": 1,
    "expedition_tier": "long",
}


PRIVATE_CATALOG_MODELS = (
    "accounts.User", "rpg.CharacterProfile", "rpg.UserInventory",
    "pets.UserPet", "pets.UserMount", "achievements.SkillProgress",
    "achievements.UserBadge", "rewards.CoinLedger", "activity.ActivityEvent",
    "quests.ChallengeActivity", "quests.ChallengeOccurrence",
)


def _assert_global_catalog_read(test_case, sql):
    # PostgreSQL wraps each SELECT in a compound query; SQLite does not.
    # Strip only opening grouping/whitespace, retaining the statement verb.
    normalized = sql.lstrip(" \t\r\n\f\v(").lower()
    test_case.assertRegex(normalized, r"^select\b", sql)
    private_tables = {apps.get_model(label)._meta.db_table for label in PRIVATE_CATALOG_MODELS}
    private_tables.update(("accounts_user", "projects_skillprogress", "projects_userbadge"))
    for table in private_tables:
        test_case.assertNotIn(f'"{table}"', normalized)


class ProgressionCatalogReadGuardTests(SimpleTestCase):
    def test_plain_and_parenthesized_global_selects_are_allowed(self):
        for sql in (
            'SELECT "id" FROM "achievements_badge"',
            '(SELECT "id" FROM "achievements_badge") UNION ALL (SELECT "id" FROM "achievements_badge")',
            ' \n ( ( SELECT "id" FROM "projects_skillcategory" ) )',
        ):
            with self.subTest(sql=sql):
                _assert_global_catalog_read(self, sql)

    def test_parenthesized_writes_are_rejected(self):
        for sql in (
            'INSERT INTO "achievements_badge" ("name") VALUES (%s)',
            'UPDATE "achievements_badge" SET "name" = %s',
            'DELETE FROM "achievements_badge"',
        ):
            for opening, closing in (("", ""), ("(", ")"), (" \n ( ( \t", ") )")):
                with self.subTest(sql=sql, opening=opening), self.assertRaises(AssertionError):
                    _assert_global_catalog_read(self, opening + sql + closing)

    def test_select_bearing_and_data_modifying_cte_writes_are_rejected(self):
        for sql in (
            'UPDATE "achievements_badge" SET "name" = %s WHERE "id" IN (SELECT "id" FROM "achievements_badge")',
            'INSERT INTO "achievements_badge" ("name") SELECT "name" FROM "achievements_badge"',
            'WITH changed AS (DELETE FROM "achievements_badge" RETURNING "id") SELECT "id" FROM changed',
        ):
            for opening, closing in (("", ""), ("(", ")"), (" \n ( ( \t", ") )")):
                with self.subTest(sql=sql, opening=opening), self.assertRaises(AssertionError):
                    _assert_global_catalog_read(self, opening + sql + closing)

    def test_real_player_models_and_independent_private_tables_are_rejected(self):
        statements = [str(apps.get_model(label).objects.values("pk").query) for label in PRIVATE_CATALOG_MODELS]
        # Independent of the guard's model list: dropping a protected model
        # must not simultaneously remove the matching negative control.
        statements += [f'SELECT "id" FROM "{table}"' for table in (
            "projects_user", "rpg_characterprofile", "rpg_userinventory",
            "pets_userpet", "pets_usermount", "achievements_skillprogress",
            "achievements_userbadge", "rewards_coinledger", "activity_activityevent",
            "quests_challengeactivity", "quests_challengeoccurrence",
            "accounts_user", "projects_skillprogress", "projects_userbadge",
        )]
        for sql in statements:
            for statement in (sql, f"({sql})", f'(SELECT "id" FROM "achievements_badge") UNION ALL ({sql})'):
                with self.subTest(sql=statement), self.assertRaises(AssertionError):
                    _assert_global_catalog_read(self, statement)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class ProgressionCatalogParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_snapshot_respects_real_acquisition_policy(self):
        catalog = load_catalog()
        expected = {
            item.pk for item in ItemDefinition.objects.select_related(
                "pet_species", "potion_type", "food_species",
            ) if item_is_available(item)
        }
        self.assertEqual(set(catalog.items), expected)
        self.assertEqual(len(catalog.pairs), 35)
        self.assertEqual({(species.slug, potion.slug) for species, potion in catalog.pairs.values()
                          if potion.slug != "base"}, {
            (species, potion) for species in ("chick", "meshtint-wolf", "meshtint-dragon", "meshtint-mushroom", "meshtint-bee", "meshtint-bat",
                                             "meshtint-snake", "meshtint-hermit-crab", "meshtint-ghost", "meshtint-potted-plant")
            for potion in ("fire", "ice")
        })
        self.assertFalse(any(item.item_type == "cosmetic_pet_accessory" for item in catalog.items.values()))
        self.assertTrue(all(entry.item_id in expected for pool in catalog.pools.values() for entry in pool))

    def test_drop_changes_invalidate_saved_forecast_fingerprint(self):
        before = load_catalog().fingerprint
        entry = DropTable.objects.filter(item__item_type="food").first()
        DropTable.objects.filter(pk=entry.pk).update(weight=entry.weight + 7, min_level=3)
        after = load_catalog()
        self.assertNotEqual(before, after.fingerprint)
        saved = next(row for row in after.pools[entry.trigger_type] if row.pk == entry.pk)
        self.assertEqual((saved.weight, saved.min_level), (entry.weight + 7, 3))

    def test_simulation_reads_only_global_catalog_and_cannot_write(self):
        from apps.rpg.progression import simulate_progression

        statements = []

        def only_global_reads(execute, sql, params, many, context):
            _assert_global_catalog_read(self, sql)
            statements.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(only_global_reads):
            result = simulate_progression(dict(CONFIG))
        self.assertTrue(statements, "The real global catalog must be read.")
        self.assertEqual(result["schema_version"], 1)

    def test_same_seed_reproduces_forecast_without_using_global_random(self):
        from apps.rpg.progression import simulate_progression

        with patch("random.random", side_effect=AssertionError("Use a local seeded generator")):
            first = simulate_progression(dict(CONFIG))
            second = simulate_progression(dict(CONFIG))
        for key in ("milestones", "trace", "summary", "flows"):
            self.assertEqual(first[key], second[key], key)

    def test_loaded_trial_executes_without_database_queries(self):
        catalog = load_catalog()
        with self.assertNumQueries(0):
            report = run_trial(CONFIG, catalog, 42)
        self.assertEqual(len(report["trace"]), CONFIG["horizon_days"])

    def test_snapshot_graph_is_detached_and_immutable(self):
        catalog = snapshot_catalog()
        skill = next(iter(catalog.skills.values()))
        item = next(iter(catalog.items.values()))
        quest = catalog.quests[0]
        with self.assertRaises(FrozenInstanceError):
            skill.name = "Changed"
        with self.assertRaises(TypeError):
            catalog.items[item.pk] = item
        with self.assertRaises(TypeError):
            item.metadata["growth"] = 30
        with self.assertRaises(TypeError):
            quest.trigger_filter["allowed_triggers"] = ["habit_log"]
        self.assertIs(quest.reward_items.all(), quest.reward_items)
        self.assertFalse(hasattr(skill, "save"))
        self.assertFalse(hasattr(item, "_state"))

    def test_proposed_snapshot_survives_rollback_without_reads_or_payouts(self):
        from apps.rpg.progression import simulate_progression

        quest = QuestDefinition.objects.create(
            name="Preview-only reward", description="One synthetic habit", quest_type="collection",
            target_value=1, duration_days=7, trigger_filter={"allowed_triggers": ["habit_log"]},
            coin_reward=7, is_system=True,
        )
        baseline = snapshot_catalog()
        with transaction.atomic():
            QuestDefinition.objects.filter(pk=quest.pk).update(coin_reward=17)
            proposed = snapshot_catalog()
            transaction.set_rollback(True)
        quest.refresh_from_db()
        self.assertEqual(quest.coin_reward, 7)
        config = {**CONFIG, "trials": 1, "reading_minutes": 0, "chores_per_day": 0,
                  "journal_per_day": False, "expeditions_per_day": 0}
        with self.assertNumQueries(0):
            before = simulate_progression(config, catalog=baseline)
            after = simulate_progression(config, catalog=proposed)
            repeated = simulate_progression(config, catalog=proposed)
        self.assertEqual(before["config"], after["config"])
        self.assertNotEqual(before["catalog"]["fingerprint"], after["catalog"]["fingerprint"])
        # Added loot can change later badge timing and salvage. Compare the
        # explicitly edited promise rather than all downstream income.
        def challenge_coins(report):
            return next(row["coins"] for row in report["flows"]["sources"] if row["source"] == "challenges")
        self.assertEqual(challenge_coins(after) - challenge_coins(before), 10)
        self.assertEqual(after, repeated)

    def test_project_and_expedition_pools_match_real_service_weights(self):
        child = make_family(children=[{"username": "parity-drop-child"}]).children[0]
        food = ItemDefinition.objects.filter(item_type="food").first()
        gated = ItemDefinition.objects.create(slug="parity-high-level-food", name="Later food", item_type="food")
        DropTable.objects.create(trigger_type="clock_out", item=gated, weight=111, min_level=6)
        unsupported = ItemDefinition.objects.create(
            slug="parity-unsupported-accessory", name="Unsupported accessory", item_type="cosmetic_pet_accessory",
        )
        DropTable.objects.create(trigger_type="clock_out", item=unsupported, weight=999999)
        catalog = load_catalog()
        trial = Trial(CONFIG, catalog, 1)
        captured = []

        def select(entries, *, weights, k):
            captured.append({(row.trigger_type, row.item_id): weight for row, weight in zip(entries, weights)})
            return [next(row for row in entries if row.item_id == food.pk)]

        def assert_weights(entries, weights):
            projected = {(row.trigger_type, row.item_id): weight for row, weight in zip(entries, weights)}
            self.assertEqual(set(projected), set(captured[-1]))
            for key, weight in projected.items():
                # Runtime and snapshot iteration orders differ; tier totals
                # accumulate the same floating-point inputs in another order.
                self.assertAlmostEqual(weight, captured[-1][key], places=12, msg=str(key))

        for level, total_xp in ((0, 0), (6, 2500)):
            with self.subTest(level=level):
                CharacterProfile.objects.filter(user=child).update(level=level)
                trial.total_xp = total_xp
                with patch("apps.rpg.services.random.random", return_value=0), patch(
                    "apps.rpg.services.random.choices", side_effect=select,
                ):
                    DropService.process_drops(child, "clock_out")
                entries, weights = trial.eligible_pool("clock_out")
                assert_weights(entries, weights)
                self.assertEqual(gated.pk in {row.item_id for row in entries}, level == 6)
                self.assertNotIn(unsupported.pk, {row.item_id for row in entries})
                for tier in ("short", "standard", "long"):
                    with patch("apps.pets.expeditions.random.choices", side_effect=select):
                        ExpeditionService._roll_loot(child, tier)
                    entries, weights = trial.eligible_pool("expedition_returned", expedition_tier=tier)
                    assert_weights(entries, weights)

    def test_feeding_evolution_matches_actual_saved_growth(self):
        base = PotionType.objects.get(slug="base")
        cases = (("chick", "food-birdseed", 7), ("meshtint-bat", "food-meat", 20),
                 ("meshtint-bat", "food-stardust", 3))
        for index, (species_slug, food_slug, quantity) in enumerate(cases):
            with self.subTest(species=species_slug):
                child = make_family(children=[{"username": f"parity-feed-{index}"}]).children[0]
                species = PetSpecies.objects.get(slug=species_slug)
                food = ItemDefinition.objects.get(slug=food_slug)
                pet = UserPet.objects.create(user=child, species=species, potion=base)
                UserInventory.objects.create(user=child, item=food, quantity=quantity)
                trial = Trial(CONFIG, load_catalog(), 1)
                trial.day = 1
                pair = (species.pk, base.pk)
                trial.pets[pair] = SimPet(species, base)
                trial.inventory[food.pk] = quantity
                trial.feed_and_hatch()
                for _ in range(quantity):
                    PetService.feed_pet(child, pet.pk, food.pk)
                pet.refresh_from_db()
                projected = trial.pets[pair]
                self.assertEqual((projected.growth_points, projected.evolved_to_mount),
                                 (pet.growth_points, pet.evolved_to_mount))
                if quantity >= 7:
                    self.assertEqual((pet.growth_points, pet.evolved_to_mount), (100, True))
                self.assertEqual(trial.inventory[food.pk], 0)
                self.assertFalse(UserInventory.objects.filter(user=child, item=food).exists())

    def test_food_and_rarity_policy_changes_invalidate_rules_fingerprint(self):
        from apps.rpg.item_effects import FOOD_GROWTH_BY_RARITY
        from apps.rpg.rarity import BASE_TIER_WEIGHTS

        for policy, key in ((FOOD_GROWTH_BY_RARITY, "common"), (BASE_TIER_WEIGHTS, "rare")):
            before = rules_fingerprint()
            with patch.dict(policy, {key: policy[key] + 1}):
                self.assertNotEqual(before, rules_fingerprint())

    def test_journal_forecast_matches_native_daily_coins_and_badge_evaluation_order(self):
        child = make_family(children=[{"username": "parity-journal-child"}]).children[0]
        # A coin badge must wait until the next real XP/badge evaluation:
        # journal XP is processed before today's direct coin recognition.
        coin_badge = Badge.objects.create(
            name="Journal coin ordering", criteria_type="total_coins_earned",
            criteria_value={"amount": 1}, xp_bonus=0, award_coins=False,
        )
        catalog = replace(load_catalog(), badges=[coin_badge], quests=[])
        config = {**CONFIG, "reading_minutes": 0, "chores_per_day": 0,
                  "habits_per_day": 0, "expeditions_per_day": 0, "journal_per_day": True}
        trial = Trial(config, catalog, 42)
        # Keep only the badge under test in the real evaluator as well.
        Badge.objects.exclude(pk=coin_badge.pk).delete()
        today = timezone.localdate()
        for day in (1, 2):
            with self.subTest(day=day), patch(
                "django.utils.timezone.localdate", return_value=today + timedelta(days=day - 1),
            ), patch("apps.rpg.services.DropService.process_drops", return_value=None), patch.object(trial, "drop"):
                entry = ChronicleService.write_journal(child, title="A short reflection", summary="A few words count.")
                trial.daily(day)
                self.assertEqual(entry.metadata["reward_receipt"]["coins_awarded"], GRATITUDE_FIRST_OF_DAY_COINS)
                self.assertEqual(trial.source_totals["journal"]["coins"], day * GRATITUDE_FIRST_OF_DAY_COINS)
                self.assertEqual(trial.coins, CoinService.get_balance(child))
                self.assertEqual(trial.badges, set(UserBadge.objects.filter(user=child).values_list("badge_id", flat=True)))
                self.assertEqual(coin_badge.pk in trial.badges, day == 2)

    def test_journal_coin_policy_changes_invalidate_saved_rules_fingerprint(self):
        before = rules_fingerprint()
        with patch(
            "apps.rpg.progression.engine.GRATITUDE_FIRST_OF_DAY_COINS",
            GRATITUDE_FIRST_OF_DAY_COINS + 1, create=True,
        ):
            self.assertNotEqual(before, rules_fingerprint())

    def test_expedition_avoids_duplicate_cosmetics_within_its_prerolled_trip(self):
        child = make_family(children=[{"username": "parity-expedition-child"}]).children[0]
        cosmetics = [ItemDefinition.objects.create(
            slug=f"parity-trip-frame-{index}", name=f"Trip frame {index}",
            item_type="cosmetic_frame", rarity="common", coin_value=5,
        ) for index in range(2)]
        for item in cosmetics:
            DropTable.objects.create(trigger_type="expedition_returned", item=item, weight=1)

        def first_positive(entries, *, weights, k):
            return [next(entry for entry, weight in zip(entries, weights) if weight > 0)]

        with patch("apps.pets.expeditions.random.choices", side_effect=first_positive):
            actual = ExpeditionService._roll_loot(child, "standard")
        trial = Trial({**CONFIG, "expedition_tier": "standard"}, load_catalog(), 1)
        pair, (species, potion) = next(iter(trial.catalog.pairs.items()))
        trial.pets[pair] = SimPet(species, potion, 100, True)
        with patch.object(trial.rng, "choices", side_effect=first_positive):
            trial.launch_expeditions()
        self.assertEqual(trial.pending_expeditions[0]["items"], [row["item_id"] for row in actual["items"]])
        self.assertEqual(len(set(trial.pending_expeditions[0]["items"])), 2)

    def test_finite_expedition_targets_respect_zero_weight_and_excluded_rarity(self):
        rows = [ItemDefinition.objects.create(
            slug=f"parity-expedition-target-{index}", name=f"Expedition target {index}",
            item_type="cosmetic_frame", rarity=rarity,
        ) for index, rarity in enumerate(("common", "legendary", "rare"))]
        for index, item in enumerate(rows):
            DropTable.objects.create(trigger_type="expedition_returned", item=item, weight=0 if index == 2 else 1)
        trial = Trial({**CONFIG, "expedition_tier": "short"}, load_catalog(), 1)
        self.assertIn(f"cosmetic:{rows[0].pk}", trial.finite_keys)
        self.assertNotIn(f"cosmetic:{rows[1].pk}", trial.finite_keys)
        self.assertNotIn(f"cosmetic:{rows[2].pk}", trial.finite_keys)

    def test_guaranteed_trails_can_hatch_without_random_drops(self):
        catalog = load_catalog()
        config = {**CONFIG, "trials": 1, "reading_minutes": 0, "chores_per_day": 1,
                  "habits_per_day": 0, "journal_per_day": False, "expeditions_per_day": 0}
        with patch.object(Trial, "drop"):
            report = run_trial(config, catalog, 42)
        self.assertIn("first_pet", report["milestones"])
        messages = audit_catalog(catalog)
        self.assertTrue(any(row["code"] == "guaranteed_companion_paths" for row in messages))
        self.assertFalse(any("no assumed starter pet or guaranteed egg/potion" in row["message"] for row in messages))

    def test_one_source_advances_multiple_catalog_challenges(self):
        child = make_family(children=[{"username": "parity-goal-child"}]).children[0]
        now = timezone.now()
        definitions = [QuestDefinition.objects.create(
            name=f"Parity concurrent {index}", description="Same factual action",
            quest_type="collection", target_value=1, duration_days=7,
            coin_reward=0, xp_reward=0, is_system=True,
            trigger_filter={"allowed_triggers": ["habit_log"]},
        ) for index in range(2)]
        trial = Trial(CONFIG, load_catalog(), 1)
        trial.day = 1
        trial.event("habit_log", drops=False)
        # The trusted ingestion seam accepts a durable source identity and
        # measures every eligible goal independently of Today pin state.
        with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=1)):
            ingest_activity(child, "habit_log", "parity-source", "habit_log", occurred_at=now + timedelta(seconds=1))
        for definition in definitions:
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition, goal__user=child)
            self.assertEqual((occurrence.progress, occurrence.status), (Decimal(1), "completed"))
            self.assertIn(definition.pk, trial.completed_quests)
            self.assertEqual(trial.quest_windows[definition.pk]["progress"], occurrence.progress)

    def test_from_zero_without_rewarded_sources_never_invents_a_pet_or_balance(self):
        config = {**CONFIG, "trials": 1, "reading_minutes": 0, "project_minutes": 0,
                  "chores_per_day": 0, "habits_per_day": 0,
                  "movement_sessions_per_day": 0, "creations_per_day": 0,
                  "journal_per_day": False}
        report = run_trial(config, load_catalog(), 42)
        self.assertNotIn("first_pet", report["milestones"])
        self.assertFalse(report["sources"])
        for row in report["trace"]:
            self.assertEqual((row["coins"], row["total_xp"], row["pets"], row["mounts"]), (0, 0, 0, 0))

    def test_reading_without_ingredient_promises_cannot_bootstrap_mounts_from_expedition_loot(self):
        config = {**CONFIG, "trials": 1, "chores_per_day": 0, "habits_per_day": 0,
                  "journal_per_day": False}
        catalog = replace(load_catalog(), quests=[])
        trial = Trial(config, catalog, 42)
        self.assertFalse(any(key.startswith(("pet:", "middle:", "mount:")) for key in trial.finite_keys))
        report = run_trial(config, catalog, 42)
        self.assertGreater(report["trace"][-1]["coins"], 0)
        self.assertNotIn("first_pet", report["milestones"])
        self.assertEqual(report["trace"][-1]["pets"], 0)

    def test_reading_only_can_earn_elemental_pets_from_guaranteed_challenges_without_drops(self):
        config = {**CONFIG, "trials": 1, "chores_per_day": 0, "habits_per_day": 0,
                  "journal_per_day": False, "expeditions_per_day": 0}
        with patch.object(Trial, "drop"):
            report = run_trial(config, load_catalog(), 42)
        self.assertIn("first_pet", report["milestones"])
        self.assertGreater(report["trace"][-1]["pets"], 0)

    def test_expedition_duplicate_cosmetic_outcomes_match_real_materialization(self):
        species = PetSpecies.objects.get(slug="chick")
        potion = PotionType.objects.get(slug="base")
        for index, value in enumerate((30, 0)):
            with self.subTest(coin_value=value):
                child = make_family(children=[{"username": f"parity-salvage-{index}"}]).children[0]
                title = ItemDefinition.objects.create(
                    slug=f"parity-duplicate-title-{index}", name=f"Duplicate title {index}",
                    item_type="cosmetic_title", coin_value=value,
                )
                UserInventory.objects.create(user=child, item=title, quantity=1)
                locked = SimpleNamespace(
                    loot={"coins": 0, "items": [{"item_id": title.pk, "quantity": 1}]},
                    tier="short", mount=SimpleNamespace(species=species),
                )
                before = CoinService.get_balance(child)
                ExpeditionService._materialize_loot(child, locked)
                actual_salvage = CoinService.get_balance(child) - before
                trial = Trial(CONFIG, load_catalog(), 42)
                trial.day = 1
                pair = (species.pk, potion.pk)
                trial.pets[pair] = SimPet(species, potion, 100, True)
                trial.inventory[title.pk] = 1
                trial.pending_expeditions = [{"pair": pair, "returns": 0, "coins": 0, "items": [title.pk]}]
                trial.claim_expeditions()
                self.assertEqual(trial.source_totals["expeditions_salvage"]["coins"], actual_salvage)
                self.assertEqual(trial.inventory[title.pk], UserInventory.objects.get(user=child, item=title).quantity)

    def test_busy_day_caps_rewards_while_retaining_saved_activity_counts(self):
        trial = Trial({**CONFIG, "movement_sessions_per_day": 6,
                       "movement_minutes": 240, "movement_intensity": "high",
                       "creations_per_day": 4}, load_catalog(), 42)
        trial.daily(1)
        self.assertEqual(trial.counters["movement_sessions"], 6)
        self.assertEqual(trial.counters["movement_minutes"], 6 * 240)
        self.assertEqual(trial.counters["creations"], 4)
        self.assertEqual(trial.source_totals["movement"]["xp"],
                         MovementSessionService.DAILY_REWARD_LIMIT * MovementSessionService.compute_xp_pool(240, "high"))
        self.assertEqual(trial.source_totals["creations"]["xp"], 20)
        # 2 chores + 1 habit + 1 reading + 3 rewarded movement +
        # 2 rewarded creations + 1 journal; accomplishments draw separately.
        self.assertEqual(trial.counters["drop_opportunities:movement_session"], 3)
        self.assertEqual(trial.counters["drop_opportunities:creation_logged"], 2)
        self.assertEqual(trial.counters["drop_opportunities"], 10 + len(trial.badges) + trial.counters["quest_completions"])

    def test_maximum_horizon_keeps_trace_and_journey_bounded(self):
        config = {**CONFIG, "horizon_days": 365, "trials": 1,
                  "active_days_per_week": 7, "project_minutes": 60,
                  "movement_sessions_per_day": 1, "creations_per_day": 1,
                  "expeditions_per_day": 15}
        report = run_trial(config, load_catalog(), 42)
        self.assertEqual(len(report["trace"]), 365)
        self.assertLessEqual(len(report["events"]), 1000)
        self.assertGreater(report["event_count"], len(report["events"]))
        self.assertTrue(all(row["finite_remaining"] >= 0 for row in report["trace"]))

    def test_quest_xp_adds_reachable_badge_targets_after_direct_skill_xp(self):
        first = Skill.objects.get(name="Mindfulness", category__name="Physical")
        second = Skill.objects.create(name="Parity quest skill", category=first.category)
        quest = QuestDefinition.objects.create(
            name="Parity alternate skill", description="One factual habit",
            quest_type="collection", target_value=1, duration_days=7,
            xp_reward=100, is_system=True,
            trigger_filter={"allowed_triggers": ["habit_log"]},
        )
        QuestSkillTag.objects.create(quest_definition=quest, skill=second)
        badge = Badge.objects.create(name="Parity two leveled skills", icon="B",
                                     criteria_type="skill_level_reached",
                                     criteria_value={"count": 2, "level": 1}, xp_bonus=0)
        catalog = replace(load_catalog(), badges=[badge], quests=[quest])
        trial = Trial({**CONFIG, "reading_minutes": 0, "chores_per_day": 0,
                       "journal_per_day": False}, catalog, 42)
        child = make_family(children=[{"username": "parity-skill-child"}]).children[0]
        for skill in (first, second):
            SkillProgress.objects.create(user=child, skill=skill, xp_points=100, level=1)
        self.assertTrue(BadgeService._check_criteria(child, badge))
        self.assertIn(f"badge:{badge.pk}", trial.finite_keys)
