"""Detached care must earn the same scoped badges and payouts as live care."""
from unittest.mock import patch
from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

from django.db.models import Sum
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.pets.services import PetService
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import SimPet, Trial, rules_fingerprint
from apps.rpg.tests.test_progression_economy import quiet_config
from config.tests.factories import make_family


def alternate_pet_hook(*args, **kwargs):
    """A distinct runtime implementation for saved-forecast binding checks."""
    return None


@override_settings(
    RPG_ASSET_SUPPORT_POLICY=None,
    COINS_PER_BADGE_RARITY={"common": 7},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ProgressionPetBadgeParityTests(TestCase):
    def setUp(self):
        self.child = make_family("Care forecast", children=[{"username": "care-forecast-child"}]).children[0]
        self.species = PetSpecies.objects.create(slug="chick", name="Chick", icon="C", sprite_key="cute-chick")
        self.potion_type = PotionType.objects.create(slug="base", name="Base")
        self.species.available_potions.add(self.potion_type)
        self.egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=self.species, metadata={"species": "chick"})
        self.potion = ItemDefinition.objects.create(slug="base-potion", name="Base Potion", item_type="potion", potion_type=self.potion_type, metadata={"variant": "base"})
        self.food = ItemDefinition.objects.create(slug="birdseed", name="Birdseed", item_type="food", food_species=self.species)
        category = SkillCategory.objects.create(name="Forecast care")
        self.skill = Skill.objects.create(category=category, name="Care skill")
        self.progress = SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1, unlocked=True)
        self.hatch_badge = self.badge("A first hatch", "pets_hatched", 25)
        self.species_badge = self.badge("B first species", "pet_species_owned", 15)
        self.mount_badge = self.badge("C first evolution", "mounts_evolved", 35)
        self.meta_badge = self.badge("Z collector", "badges_earned_count", 5, count=2)
        self.coin_badge = Badge.objects.create(name="D unrelated coin badge", criteria_type="total_coins_earned", criteria_value={"amount": 1}, xp_bonus=99)
        self.now = datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc)

    def badge(self, name, kind, xp, count=1):
        return Badge.objects.create(name=name, criteria_type=kind, criteria_value={"count": count}, xp_bonus=xp)

    def trial(self, **changes):
        trial = Trial(quiet_config(**changes), load_catalog(), 42)
        trial.day = 1
        trial.xp[self.skill.pk] = 100
        trial.total_xp = 100
        return trial

    def give(self, item, quantity):
        UserInventory.objects.create(user=self.child, item=item, quantity=quantity)

    def assert_parity(self, trial, expected_badges):
        actual = set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True))
        self.assertEqual(actual, {badge.pk for badge in expected_badges})
        self.assertEqual(trial.badges, actual)
        self.progress.refresh_from_db()
        self.assertEqual(trial.xp[self.skill.pk], self.progress.xp_points)
        self.assertEqual(trial.total_xp, self.progress.xp_points)
        self.assertEqual(trial.coins, CoinLedger.objects.filter(user=self.child).aggregate(total=Sum("amount"))["total"] or 0)
        self.assertNotIn(self.coin_badge.pk, actual)

    def test_hatch_alone_matches_live_hatch_species_meta_coins_and_xp_once(self):
        # The live evaluator makes one ordered pass. An earlier meta badge
        # waits for a later real hook rather than recursively earning itself.
        earlier_meta = Badge.objects.create(name="00 earlier collector", criteria_type="badges_earned_count",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False)
        trial = self.trial(feed_strategy="none")
        for item in (self.egg, self.potion):
            self.give(item, 2)
            trial.inventory[item.pk] = 2

        with patch("django.utils.timezone.now", return_value=self.now):
            incubation, _ = PetService.start_incubation(self.child, self.egg.pk, self.potion.pk, uuid4())
        trial.feed_and_hatch()
        self.assert_parity(trial, [])
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            PetService.hatch_incubation(self.child, incubation.pk)
        trial.day = 2
        trial.claim_incubation()

        self.assert_parity(trial, [self.hatch_badge, self.species_badge, self.meta_badge])
        self.assertNotIn(earlier_meta.pk, trial.badges)
        self.assertEqual((trial.coins, trial.total_xp), (21, 145))
        before = (trial.coins, trial.total_xp, trial.event_count)
        trial.feed_and_hatch()
        self.assertFalse(PetService.hatch_incubation(self.child, incubation.pk)[2])
        with self.assertRaisesRegex(ValueError, "already have"):
            PetService.start_incubation(self.child, self.egg.pk, self.potion.pk, uuid4())
        self.assertEqual((trial.coins, trial.total_xp, trial.event_count), before)
        self.assert_parity(trial, [self.hatch_badge, self.species_badge, self.meta_badge])

    def test_evolution_alone_matches_live_feed_badge_coins_and_xp_once(self):
        pet = UserPet.objects.create(user=self.child, species=self.species, potion=self.potion_type, growth_points=85)
        BadgeService.evaluate_badges(self.child, scopes={"pet", "badges"})
        trial = self.trial()
        pair = (self.species.pk, self.potion_type.pk)
        trial.pets[pair] = SimPet(*trial.catalog.pairs[pair], growth_points=85)
        trial.evaluate_badges(scopes={"pet", "badges"})
        self.give(self.food, 2)
        trial.inventory[self.food.pk] = 2

        self.assertTrue(PetService.feed_pet(self.child, pet.pk, self.food.pk)["evolved"])
        trial.feed_and_hatch()

        expected = [self.hatch_badge, self.species_badge, self.mount_badge, self.meta_badge]
        self.assert_parity(trial, expected)
        self.assertEqual((trial.coins, trial.total_xp), (28, 180))
        before = (trial.coins, trial.total_xp, trial.event_count)
        trial.feed_and_hatch()
        with self.assertRaisesRegex(ValueError, "already evolved"):
            PetService.feed_pet(self.child, pet.pk, self.food.pk)
        self.assertEqual((trial.coins, trial.total_xp, trial.event_count), before)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, trial.inventory[self.food.pk])
        self.assert_parity(trial, expected)

    def test_middle_growth_does_not_invent_a_new_badge_hook(self):
        pet = UserPet.objects.create(user=self.child, species=self.species, potion=self.potion_type, growth_points=40)
        trial = self.trial()
        pair = (self.species.pk, self.potion_type.pk)
        trial.pets[pair] = SimPet(*trial.catalog.pairs[pair], growth_points=40)
        self.give(self.food, 1)
        trial.inventory[self.food.pk] = 1

        self.assertFalse(PetService.feed_pet(self.child, pet.pk, self.food.pk)["evolved"])
        trial.feed_and_hatch()

        self.assertEqual(trial.pets[pair].growth_points, 55)
        self.assert_parity(trial, [])

    def quest(self, name, badge):
        return QuestDefinition.objects.create(name=name, quest_type="collection", target_value=1, duration_days=30,
            is_system=True, required_badge=badge, trigger_filter={"allowed_triggers": ["habit_log"]})

    def test_pet_scope_alone_makes_hatch_badges_and_their_gated_challenge_reachable(self):
        for item in (self.egg, self.potion):
            DropTable.objects.create(trigger_type="habit_log", item=item, weight=1)
        goal = self.quest("Care-gated food", self.hatch_badge)
        QuestRewardItem.objects.create(quest_definition=goal, item=self.food, quantity=7)

        trial = self.trial(habits_per_day=1, habit_xp=0)

        self.assertTrue({f"badge:{badge.pk}" for badge in (self.hatch_badge, self.species_badge, self.mount_badge, self.meta_badge)} <= trial.finite_keys)
        self.assertIn(f"quest:{goal.pk}", trial.finite_keys)
        self.assertIn(f"mount:{(self.species.pk, self.potion_type.pk)}", trial.finite_keys)

    def test_pet_scopes_follow_new_pairs_unlocked_inside_the_reachability_fixed_point(self):
        habit_badge = self.badge("00 habit gate", "habit_taps_lifetime", 0)
        first = self.quest("Habit-gated ingredients", habit_badge)
        for item in (self.egg, self.potion):
            QuestRewardItem.objects.create(quest_definition=first, item=item)
        second = self.quest("Hatch-gated food", self.hatch_badge)
        QuestRewardItem.objects.create(quest_definition=second, item=self.food, quantity=7)

        trial = self.trial(habits_per_day=1, habit_xp=1)

        self.assertIn(f"quest:{first.pk}", trial.finite_keys)
        self.assertIn(f"quest:{second.pk}", trial.finite_keys)
        self.assertIn(f"badge:{self.hatch_badge.pk}", trial.finite_keys)
        self.assertIn(f"badge:{self.mount_badge.pk}", trial.finite_keys)

    def test_no_obtainable_pair_cannot_invent_reachable_pet_badges(self):
        trial = self.trial(habits_per_day=1, habit_xp=0)
        self.assertFalse(any(f"badge:{badge.pk}" in trial.finite_keys for badge in (self.hatch_badge, self.species_badge, self.mount_badge)))

    def test_changed_runtime_pet_hooks_invalidate_saved_forecast_rules(self):
        before = rules_fingerprint()
        for name in ("start_incubation", "hatch_incubation", "incubation_duration_seconds", "_save_growth", "_evaluate_pet_badges"):
            with self.subTest(hook=name), patch.object(PetService, name, alternate_pet_hook):
                self.assertNotEqual(before, rules_fingerprint())
