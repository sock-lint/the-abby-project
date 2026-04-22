"""Tests for the 2026-04-23 content-review consumable effects.

Pins the dispatch branches in ``ConsumableService._apply_effect`` for the
five new consumables — ``lucky_dip``, ``quest_reroll``, ``morale_tonic``,
``skill_tonic``, ``food_basket``. Each effect runs purely at the service
layer and needs no cross-service wiring.
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from apps.projects.models import User
from apps.rpg.models import (
    CharacterProfile,
    ItemDefinition,
    UserInventory,
)
from apps.rpg.services import ConsumableService


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def _consumable(slug, effect, metadata=None, **kwargs):
    meta = {"effect": effect}
    if metadata:
        meta.update(metadata)
    return ItemDefinition.objects.create(
        slug=slug,
        name=slug,
        item_type=ItemDefinition.ItemType.CONSUMABLE,
        metadata=meta,
        **{"rarity": "rare", **kwargs},
    )


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class LuckyDipEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)

    def _make_cosmetic(self, slug, rarity="uncommon"):
        return ItemDefinition.objects.create(
            slug=slug, name=slug, icon="x",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=rarity, coin_value=15,
        )

    def test_lucky_dip_grants_a_cosmetic(self):
        self._make_cosmetic("frame-a", "uncommon")
        self._make_cosmetic("frame-b", "rare")

        item = _consumable("lucky-dip", "lucky_dip", {"rarities": ["uncommon", "rare"]})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        result = ConsumableService.use(self.user, item.pk)
        detail = result["detail"]
        self.assertIn("granted_item_id", detail)
        self.assertIn(detail["granted_rarity"], {"uncommon", "rare"})

    def test_lucky_dip_salvages_when_already_owned(self):
        from apps.rewards.models import CoinLedger

        frame = self._make_cosmetic("frame-a", "uncommon")
        # User already owns it — next lucky_dip call must salvage, not dup.
        UserInventory.objects.create(user=self.user, item=frame, quantity=1)

        # Only one eligible cosmetic in the pool, so lucky_dip MUST pick it.
        item = _consumable("lucky-dip", "lucky_dip", {"rarities": ["uncommon"]})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        result = ConsumableService.use(self.user, item.pk)
        self.assertTrue(result["detail"]["salvaged"])
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.user, amount=frame.coin_value,
            ).exists()
        )

    def test_lucky_dip_raises_when_no_eligible(self):
        item = _consumable("lucky-dip", "lucky_dip", {"rarities": ["legendary"]})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.user, item.pk)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class QuestRerollEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)

    def test_quest_reroll_spawns_an_eligible_quest(self):
        from apps.quests.models import Quest, QuestDefinition

        QuestDefinition.objects.create(
            name="Eligible",
            description="x",
            quest_type=QuestDefinition.QuestType.BOSS,
            target_value=100,
            duration_days=7,
            is_system=True,
        )
        item = _consumable("quest-reroll", "quest_reroll")
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        result = ConsumableService.use(self.user, item.pk)
        self.assertIn("quest_id", result["detail"])
        self.assertTrue(
            Quest.objects.filter(
                pk=result["detail"]["quest_id"], status=Quest.Status.ACTIVE,
            ).exists()
        )

    def test_quest_reroll_fails_when_user_has_active_quest(self):
        from django.utils import timezone
        from apps.quests.models import Quest, QuestDefinition, QuestParticipant

        defn = QuestDefinition.objects.create(
            name="Existing",
            description="x",
            quest_type=QuestDefinition.QuestType.BOSS,
            target_value=100,
            duration_days=7,
            is_system=True,
        )
        active = Quest.objects.create(
            definition=defn,
            end_date=timezone.now() + timezone.timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=active, user=self.user)

        item = _consumable("quest-reroll", "quest_reroll")
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.user, item.pk)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class MoraleTonicEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)

    def test_morale_tonic_adds_to_growth_boost(self):
        item = _consumable("pet-morale-tonic", "morale_tonic", {"feeds": 5})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        ConsumableService.use(self.user, item.pk)
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.pet_growth_boost_remaining, 5)

    def test_morale_tonic_stacks_with_growth_tonic(self):
        # Stacks additively with an existing growth_tonic counter.
        profile = CharacterProfile.objects.get(user=self.user)
        profile.pet_growth_boost_remaining = 3
        profile.save(update_fields=["pet_growth_boost_remaining"])

        item = _consumable("pet-morale-tonic", "morale_tonic", {"feeds": 5})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        ConsumableService.use(self.user, item.pk)
        profile.refresh_from_db()
        self.assertEqual(profile.pet_growth_boost_remaining, 8)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class SkillTonicEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)

    def test_skill_tonic_adds_xp_to_highest_level_skill(self):
        from apps.achievements.models import (
            Skill,
            SkillCategory,
            SkillProgress,
        )

        cat = SkillCategory.objects.create(name="Test")
        s_lead = Skill.objects.create(category=cat, name="Lead")
        s_other = Skill.objects.create(category=cat, name="Other")
        SkillProgress.objects.create(user=self.user, skill=s_lead, level=2, xp_points=350)
        SkillProgress.objects.create(user=self.user, skill=s_other, level=1, xp_points=150)

        item = _consumable("skill-tonic", "skill_tonic", {"xp": 50})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        ConsumableService.use(self.user, item.pk)
        lead_progress = SkillProgress.objects.get(user=self.user, skill=s_lead)
        other_progress = SkillProgress.objects.get(user=self.user, skill=s_other)
        self.assertEqual(lead_progress.xp_points, 400)
        self.assertEqual(other_progress.xp_points, 150)  # unchanged

    def test_skill_tonic_raises_when_no_skills(self):
        item = _consumable("skill-tonic", "skill_tonic", {"xp": 50})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.user, item.pk)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class FoodBasketEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)

    def test_food_basket_grants_N_random_foods(self):
        ItemDefinition.objects.create(
            slug="food-a", name="Food A", icon="🍖",
            item_type=ItemDefinition.ItemType.FOOD, rarity="common",
        )
        ItemDefinition.objects.create(
            slug="food-b", name="Food B", icon="🍎",
            item_type=ItemDefinition.ItemType.FOOD, rarity="common",
        )

        item = _consumable("autumns-gift", "food_basket", {"count": 2})
        UserInventory.objects.create(user=self.user, item=item, quantity=1)

        result = ConsumableService.use(self.user, item.pk)
        self.assertEqual(len(result["detail"]["granted"]), 2)
        # Every granted slug is in the food pool.
        granted_slugs = {
            ItemDefinition.objects.get(pk=g["item_id"]).slug
            for g in result["detail"]["granted"]
        }
        self.assertTrue(granted_slugs.issubset({"food-a", "food-b"}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ConsumableGrowthDailyCapTests(TestCase):
    """Pins the 2026-04-23 per-pet daily cap on consumable-driven growth."""

    def setUp(self):
        from apps.pets.models import PetSpecies, PotionType, UserPet
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)
        self.species = PetSpecies.objects.create(slug="wolf", name="Wolf", icon="🐺")
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(
            user=self.user, species=self.species, potion=self.potion,
            is_active=True, growth_points=0,
        )

    def _stack_inventory(self, slug, effect, growth, qty):
        item = _consumable(slug, effect, {"growth": growth})
        UserInventory.objects.create(user=self.user, item=item, quantity=qty)
        return item

    def test_growth_surge_caps_at_50_per_day(self):
        # 4× +30 surges would naturally add 120; cap clamps the second hit
        # to fill exactly the remaining 20, then later hits add 0.
        item = self._stack_inventory("growth-surge", "growth_surge", 30, 4)

        first = ConsumableService.use(self.user, item.pk)
        self.assertEqual(first["detail"]["growth_added"], 30)
        self.assertFalse(first["detail"]["growth_capped"])

        second = ConsumableService.use(self.user, item.pk)
        self.assertEqual(second["detail"]["growth_added"], 20)
        self.assertTrue(second["detail"]["growth_capped"])

        third = ConsumableService.use(self.user, item.pk)
        self.assertEqual(third["detail"]["growth_added"], 0)
        self.assertTrue(third["detail"]["growth_capped"])

        self.pet.refresh_from_db()
        # Cap is 50; pet started at 0, so growth lands at 50 even after 3
        # surges spending 90 points worth of consumables.
        self.assertEqual(self.pet.growth_points, 50)
        self.assertEqual(self.pet.consumable_growth_today, 50)

    def test_cap_resets_on_a_new_local_day(self):
        from datetime import timedelta
        from django.utils import timezone

        item = self._stack_inventory("growth-surge", "growth_surge", 30, 2)
        ConsumableService.use(self.user, item.pk)
        ConsumableService.use(self.user, item.pk)

        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 50)

        # Roll the counter back a day to simulate next-day usage.
        self.pet.consumable_growth_date = timezone.localdate() - timedelta(days=1)
        self.pet.save(update_fields=["consumable_growth_date"])

        UserInventory.objects.create(
            user=self.user, item=item, quantity=1,
        )
        result = ConsumableService.use(self.user, item.pk)
        # Fresh day → counter reset → first 30 lands in full again.
        self.assertEqual(result["detail"]["growth_added"], 30)
        self.assertFalse(result["detail"]["growth_capped"])

    def test_feast_platter_caps_each_pet_independently(self):
        from apps.pets.models import PotionType, UserPet
        # Second pet: feast_platter should reach BOTH unevolved pets and
        # each gets its own per-pet cap counter.
        UserPet.objects.create(
            user=self.user, species=self.species,
            potion=PotionType.objects.create(slug="fire", name="Fire"),
            growth_points=45,
        )
        item = self._stack_inventory("feast-platter", "feast_platter", 10, 1)
        result = ConsumableService.use(self.user, item.pk)
        # Both pets received 10 (each well under their cap) on their own
        # counters — the cap is per-pet, not per-user.
        self.assertEqual(result["detail"]["pets_fed"], 2)
        self.assertEqual(set(result["detail"]["growth_per_pet_applied"]), {10})
