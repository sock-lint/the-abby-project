"""Accomplishment loot stays detached and follows the live one-payout boundary."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.pets.models import PetSpecies, PotionType
from apps.quests.goals import ingest_activity
from apps.quests.models import ChallengeOccurrence, QuestDefinition
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, coverage, rules_fingerprint
from apps.rpg.services import DropService
from apps.rpg.tests.test_progression_economy import quiet_config
from config.tests.factories import make_family


def alternate_hook(*args, **kwargs):
    return None


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionAccomplishmentLootTests(TestCase):
    def setUp(self):
        self.child = make_family("Loot forecast", children=[{"username": "loot-forecast-child"}]).children[0]
        self.badge_loot = ItemDefinition.objects.create(slug="badge-prize", name="Badge prize", item_type="food")
        self.quest_loot = ItemDefinition.objects.create(slug="quest-prize", name="Quest prize", item_type="food")
        DropTable.objects.create(trigger_type="badge_earned", item=self.badge_loot, weight=1)
        DropTable.objects.create(trigger_type="quest_complete", item=self.quest_loot, weight=1)

    def badge(self, name="Habit recognition", **changes):
        return Badge.objects.create(name=name, criteria_type="habit_taps_lifetime", criteria_value={"count": 0},
                                    xp_bonus=0, award_coins=False, **changes)

    def quest(self, name="Habit challenge", **changes):
        return QuestDefinition.objects.create(name=name, quest_type="collection", target_value=1,
            duration_days=2, is_system=True, trigger_filter={"allowed_triggers": ["habit_log"]}, **changes)

    def trial(self, **changes):
        trial = Trial(quiet_config(habits_per_day=1, habit_xp=1, **changes), load_catalog(), 42)
        trial.day = 1
        return trial

    def test_new_badge_grants_one_live_parity_drop_without_effort_rewards_or_repeat(self):
        badge = self.badge()
        trial = self.trial()
        BadgeService.evaluate_badges(self.child, scopes={"habit", "badges"})
        with self.assertNumQueries(0), patch.object(DropService, "process_drops", side_effect=AssertionError("live writer")):
            trial.evaluate_badges(scopes={"habit", "badges"})
            trial.evaluate_badges(scopes={"habit", "badges"})
        self.assertEqual(trial.badges, {badge.pk})
        self.assertEqual(trial.inventory[self.badge_loot.pk], 1)
        self.assertEqual(trial.inventory[self.badge_loot.pk], UserInventory.objects.get(user=self.child, item=self.badge_loot).quantity)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type="badge_earned").count(), 1)
        self.assertEqual((trial.streak, trial.last_active, trial.counters["quest_completions"]), (0, 0, 0))
        self.assertEqual(UserBadge.objects.filter(user=self.child).count(), 1)

    def test_parallel_challenges_each_grant_once_and_repeat_window_gets_new_drop(self):
        one_off = self.quest()
        repeat = self.quest("Repeat challenge", is_repeatable=True)
        trial = self.trial()
        with self.assertNumQueries(0):
            trial.advance_challenges("habit_log", {})
            trial.advance_challenges("habit_log", {})
        self.assertEqual(trial.completed_quests, {one_off.pk, repeat.pk})
        self.assertEqual(trial.inventory[self.quest_loot.pk], 2)
        trial.day = 3
        trial.advance_challenges("habit_log", {})
        trial.advance_challenges("habit_log", {})
        self.assertEqual(trial.inventory[self.quest_loot.pk], 3)
        self.assertEqual(trial.counters["quest_completions"], 3)
        self.assertEqual((trial.streak, trial.last_active), (0, 0))

    def test_completed_automatic_goal_matches_live_drop_and_does_not_advance_other_goal(self):
        goal = self.quest()
        boss = QuestDefinition.objects.create(name="Longer boss", quest_type="boss", target_value=7,
            duration_days=2, is_system=True, trigger_filter={"allowed_triggers": ["habit_log"]})
        trial = self.trial()
        ingest_activity(self.child, "test_habit", "one", "habit_log")
        with self.assertNumQueries(0):
            trial.advance_challenges("habit_log", {})
        self.assertEqual(ChallengeOccurrence.objects.filter(status="completed").count(), 1)
        self.assertEqual(trial.completed_quests, {goal.pk})
        self.assertEqual(trial.inventory[self.quest_loot.pk], 1)
        self.assertEqual(trial.inventory[self.quest_loot.pk], UserInventory.objects.get(user=self.child, item=self.quest_loot).quantity)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type="quest_complete").count(), 1)
        self.assertEqual(trial.quest_windows[boss.pk]["progress"], 5)
        self.assertEqual(ChallengeOccurrence.objects.get(snapshot__name=boss.name).progress, 5)

    def test_accomplishment_only_cosmetics_are_reachable_after_their_source(self):
        badge = self.badge()
        self.quest()
        for trigger in ("badge_earned", "quest_complete"):
            item = ItemDefinition.objects.create(slug=trigger + "-frame", name=trigger + " frame", item_type="cosmetic_frame")
            DropTable.objects.create(trigger_type=trigger, item=item, weight=1)
        trial = self.trial()
        self.assertIn(f"badge:{badge.pk}", trial.finite_keys)
        frames = ItemDefinition.objects.filter(item_type="cosmetic_frame")
        self.assertTrue({f"cosmetic:{item.pk}" for item in frames} <= trial.finite_keys)

    def test_unreachable_accomplishment_does_not_invent_a_drop_source(self):
        Badge.objects.create(name="No hatch source", criteria_type="pets_hatched", criteria_value={"count": 1}, award_coins=False)
        item = ItemDefinition.objects.create(slug="unreachable-frame", name="Unreachable frame", item_type="cosmetic_frame")
        DropTable.objects.create(trigger_type="badge_earned", item=item, weight=1)
        self.assertNotIn(f"cosmetic:{item.pk}", self.trial().finite_keys)

    def test_badge_only_ingredients_can_reach_first_mount_and_expedition_challenge(self):
        for index in range(3):
            self.badge(f"Ingredient badge {index}")
        species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        potion = PotionType.objects.create(slug="base", name="Base")
        species.available_potions.add(potion)
        for item in (
            ItemDefinition.objects.create(slug="chick-egg", name="Egg", item_type="egg", pet_species=species,
                                          metadata={"species": "chick"}),
            ItemDefinition.objects.create(slug="base-potion", name="Potion", item_type="potion", potion_type=potion,
                                          metadata={"variant": "base"}),
        ):
            DropTable.objects.create(trigger_type="badge_earned", item=item, weight=1)
        expedition_goal = QuestDefinition.objects.create(name="First trip", quest_type="collection", target_value=1,
            duration_days=2, is_system=True, trigger_filter={"allowed_triggers": ["expedition_returned"]})
        trial = self.trial(expeditions_per_day=1)
        self.assertIn(f"mount:{(species.pk, potion.pk)}", trial.finite_keys)
        self.assertIn("expedition_returned", trial._enabled_triggers())
        self.assertIn(f"quest:{expedition_goal.pk}", trial.finite_keys)

    def test_repeatable_only_completion_reports_withheld_commitment_pool_path(self):
        repeat = self.quest(is_repeatable=True)
        pouch = ItemDefinition.objects.create(slug="quest-large-pouch", name="Large pouch",
                                              item_type="coin_pouch", coin_value=100)
        DropTable.objects.create(trigger_type="quest_complete", item=pouch, weight=1)
        trial = self.trial(reward_commitment={"enabled": True})
        self.assertFalse(any(key.startswith("quest:") for key in trial.finite_keys))
        self.assertIn(repeat.pk, trial.reachable_quest_ids)
        self.assertEqual([(row["source"], row["item_id"], row["maximum_available_coins"])
                          for row in trial.reward_commitment.affected_paths], [("quest_complete", pouch.pk, 25)])

    def test_perfect_day_pool_excludes_common_and_coverage_preserves_omission(self):
        common = ItemDefinition.objects.create(slug="perfect-common", name="Common", item_type="food")
        rare = ItemDefinition.objects.create(slug="perfect-rare", name="Rare", item_type="food", rarity="rare")
        for item in (common, rare):
            DropTable.objects.create(trigger_type="perfect_day", item=item, weight=1)
        trial = self.trial()
        entries, weights = trial.eligible_pool("perfect_day")
        self.assertNotIn(common.pk, {row.item_id for row, weight in zip(entries, weights) if weight > 0})
        self.assertIn(rare.pk, {row.item_id for row, weight in zip(entries, weights) if weight > 0})
        self.assertTrue(any("Perfect Day" in value for value in coverage(trial.catalog)["excluded"]))

    def test_changed_accomplishment_writer_invalidates_rules(self):
        before = rules_fingerprint()
        with patch.object(DropService, "award_accomplishment", alternate_hook):
            self.assertNotEqual(before, rules_fingerprint())
