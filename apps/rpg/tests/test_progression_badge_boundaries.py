"""Detached badge evaluation follows source and inventory mutation boundaries."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements import criteria
from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.habits.models import Habit
from apps.habits.services import HabitService
from apps.rpg.inventory import grant_item
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, coverage, rules_fingerprint
from apps.rpg.progression.experiments import _stale
from apps.rpg.tests.test_progression_economy import quiet_config
from config.tests.factories import make_family


def alternate_checker(user, criterion):
    return False


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class ProgressionBadgeBoundaryTests(TestCase):
    def frame(self, slug):
        return ItemDefinition.objects.create(slug=slug, name=slug, item_type="cosmetic_frame")

    def collection(self, name, *items):
        return Badge.objects.create(name=name, criteria_type="cosmetic_set_owned",
            criteria_value={"slugs": [item.slug for item in items]}, xp_bonus=0, award_coins=False)

    def trial(self, **changes):
        trial = Trial(quiet_config(**changes), load_catalog(), 42)
        trial.day = 1
        return trial

    def test_zero_xp_habit_earns_its_badge_without_inventing_xp(self):
        badge = Badge.objects.create(name="First tap", criteria_type="habit_taps_lifetime",
                                    criteria_value={"count": 1}, xp_bonus=0, award_coins=False)
        trial = self.trial(habits_per_day=1, habit_xp=0)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertIn(badge.pk, trial.badges)
        self.assertIn(f"badge:{badge.pk}", trial.finite_keys)
        self.assertEqual(trial.total_xp, 0)
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)

    def test_zero_xp_habit_badge_matches_live_positive_tap(self):
        child = make_family("Habit parity", children=[{"username": "habit-parity-child"}]).children[0]
        badge = Badge.objects.create(name="First quiet tap", criteria_type="habit_taps_lifetime",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False)
        habit = Habit.objects.create(user=child, created_by=child, name="A zero-XP habit", habit_type="positive", xp_reward=0)
        trial = self.trial(habits_per_day=1, habit_xp=0)
        HabitService.log_tap(child, habit, 1)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertEqual(trial.badges, {badge.pk})
        self.assertEqual(trial.badges, set(UserBadge.objects.filter(user=child).values_list("badge_id", flat=True)))
        self.assertEqual(trial.total_xp, 0)

    def test_authored_inventory_grant_earns_collection_badge_immediately_once(self):
        frame = self.frame("gift-frame")
        badge = self.collection("Gift collection", frame)
        trial = self.trial()
        with self.assertNumQueries(0):
            trial.grant_item(frame.pk, 1, "challenges")
            trial.grant_item(frame.pk, 1, "challenges")
        self.assertEqual(trial.badges, {badge.pk})
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)
        self.assertEqual((trial.streak, trial.last_active, trial.counters["quest_completions"]), (0, 0, 0))

    def test_inventory_grant_matches_live_collection_badge_and_completion_loot(self):
        child = make_family("Collection parity", children=[{"username": "collection-parity-child"}]).children[0]
        frame = self.frame("parity-frame")
        reward = ItemDefinition.objects.create(slug="parity-snack", name="Snack", item_type="food")
        badge = self.collection("Parity collection", frame)
        DropTable.objects.create(trigger_type="badge_earned", item=reward, weight=1)
        trial = self.trial()
        grant_item(child, frame)
        with self.assertNumQueries(0):
            trial.grant_item(frame.pk, 1, "challenges")
        self.assertEqual(trial.badges, {badge.pk})
        self.assertEqual(trial.badges, set(UserBadge.objects.filter(user=child).values_list("badge_id", flat=True)))
        self.assertEqual(dict(trial.inventory), dict(UserInventory.objects.filter(user=child).values_list("item_id", "quantity")))
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], DropLog.objects.filter(user=child).count())

    def test_random_inventory_grant_earns_badge_without_a_later_unscoped_activity(self):
        frame = self.frame("drop-frame")
        badge = self.collection("Drop collection", frame)
        DropTable.objects.create(trigger_type="habit_log", item=frame, weight=1)
        trial = self.trial(habits_per_day=1, habit_xp=0)
        with self.assertNumQueries(0), patch.object(trial.rng, "random", return_value=0):
            trial.daily(1)
        self.assertIn(badge.pk, trial.badges)
        self.assertIn(f"badge:{badge.pk}", trial.finite_keys)

    def test_badge_drop_chain_drains_without_recursion_or_repeated_rewards(self):
        frames = [self.frame(f"chain-frame-{index}") for index in range(12)]
        # Each next prerequisite sorts before the badge whose drop supplies it.
        badges = [self.collection(f"Collection {11 - index:02}", frame) for index, frame in enumerate(frames)]
        for frame in frames[1:]:
            DropTable.objects.create(trigger_type="badge_earned", item=frame, weight=1)
        trial = self.trial()
        selections = iter(frames[1:] + [frames[-1]])

        def select(entries, *, weights, k):
            item = next(selections)
            return [next(entry for entry in entries if entry.item_id == item.pk)]

        with self.assertNumQueries(0), patch.object(trial.rng, "choices", side_effect=select):
            trial.grant_item(frames[0].pk, 1, "challenges")
        self.assertEqual(trial.badges, {badge.pk for badge in badges})
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], len(badges))
        self.assertEqual((trial.streak, trial.counters["quest_completions"], trial.total_xp), (0, 0, 0))
        self.assertEqual(len([event for event in trial.events if event["source"] == "badge_earned"]), len(badges))

    def test_one_badge_draw_cannot_prove_two_collection_items(self):
        first, second = self.frame("one-slot-a"), self.frame("one-slot-b")
        starter = Badge.objects.create(name="A tap", criteria_type="habit_taps_lifetime",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False)
        collection = self.collection("B two-item collection", first, second)
        for item in (first, second):
            DropTable.objects.create(trigger_type="badge_earned", item=item, weight=1)
        trial = self.trial(habits_per_day=1, habit_xp=0)
        self.assertIn(f"badge:{starter.pk}", trial.finite_keys)
        self.assertNotIn(f"badge:{collection.pk}", trial.finite_keys)

    def test_badge_scope_changes_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        binding = {"engine_version": "same-engine", "rules_fingerprint": before,
                   "catalog_fingerprint": "same-catalog", "feedback_fingerprint": "same-feedback"}
        experiment = SimpleNamespace(revision=1)
        comparison = SimpleNamespace(experiment_revision=1, binding=binding)
        self.assertFalse(_stale(experiment, comparison, binding))
        with patch.dict(criteria._CRITERIA_SCOPES, {"habit_taps_lifetime": frozenset({"time"})}):
            after = rules_fingerprint()
            self.assertNotEqual(before, after)
            self.assertTrue(_stale(experiment, comparison, {**binding, "rules_fingerprint": after}))

    def test_registered_checker_changes_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        with patch.dict(criteria._CRITERIA_CHECKERS, {"habit_taps_lifetime": alternate_checker}):
            self.assertNotEqual(before, rules_fingerprint())

    def test_inventory_award_hook_changes_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        with patch.object(BadgeService, "evaluate_inventory_badges", alternate_checker, create=True):
            self.assertNotEqual(before, rules_fingerprint())

    def test_consumable_and_perfect_day_mechanics_remain_explicitly_excluded(self):
        omitted = ("streak_freeze_used", "consumable_variety", "perfect_days_count")
        for kind in omitted:
            Badge.objects.create(name=kind, criteria_type=kind, criteria_value={"count": 1})
        trial = self.trial()
        excluded = coverage(trial.catalog)["excluded"]
        self.assertTrue(any("Consumable use" in line for line in excluded))
        self.assertTrue(any("Perfect Day" in line for line in excluded))
        for criterion in omitted:
            self.assertFalse(any(badge.criteria_type == criterion for badge in trial.catalog.badges))
            self.assertEqual(trial.catalog.excluded_badges[criterion], 1)
