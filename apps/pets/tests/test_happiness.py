"""Tests for the 2026-04-23 pet happiness/decay feature.

Pins the ``happiness_for_pet`` buckets and the ``last_fed_at`` stamp on
``PetService.feed_pet``.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.pets.services import PetService, happiness_for_pet
from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory


def _set_last_fed(pet, days_ago):
    """Manually move last_fed_at back so we can assert against thresholds."""
    pet.last_fed_at = timezone.now() - timedelta(days=days_ago)
    pet.save(update_fields=["last_fed_at"])


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class HappinessBucketTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.species = PetSpecies.objects.create(slug="wolf", name="Wolf")
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(
            user=self.user, species=self.species, potion=self.potion,
            last_fed_at=timezone.now(),
        )

    def test_happy_when_recently_fed(self):
        _set_last_fed(self.pet, days_ago=1)
        self.assertEqual(happiness_for_pet(self.pet), "happy")

    def test_bored_after_four_days(self):
        _set_last_fed(self.pet, days_ago=5)
        self.assertEqual(happiness_for_pet(self.pet), "bored")

    def test_stale_after_eight_days(self):
        _set_last_fed(self.pet, days_ago=10)
        self.assertEqual(happiness_for_pet(self.pet), "stale")

    def test_away_after_fifteen_days(self):
        _set_last_fed(self.pet, days_ago=20)
        self.assertEqual(happiness_for_pet(self.pet), "away")

    def test_evolved_pet_is_always_happy(self):
        _set_last_fed(self.pet, days_ago=30)
        self.pet.evolved_to_mount = True
        self.pet.save(update_fields=["evolved_to_mount"])
        self.assertEqual(happiness_for_pet(self.pet), "happy")


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class FeedStampsLastFedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.species = PetSpecies.objects.create(
            slug="wolf", name="Wolf", food_preference="meat",
        )
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(
            user=self.user, species=self.species, potion=self.potion,
        )
        # Create a meat food item the pet prefers.
        self.food = ItemDefinition.objects.create(
            slug="meat",
            name="Meat",
            icon="🥩",
            item_type=ItemDefinition.ItemType.FOOD,
            metadata={"food_type": "meat", "growth": 15},
            food_species=self.species,
        )
        UserInventory.objects.create(user=self.user, item=self.food, quantity=1)

    def test_feed_pet_stamps_last_fed_at(self):
        self.assertIsNone(self.pet.last_fed_at)
        PetService.feed_pet(self.user, self.pet.pk, self.food.pk)
        self.pet.refresh_from_db()
        self.assertIsNotNone(self.pet.last_fed_at)
