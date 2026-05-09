"""Tests for the 2026-04-23 pet-breeding mechanic.

Covers ``PetService.breed_mounts`` — ownership checks, cooldown enforcement,
egg+potion deposit, and the chromatic-upgrade wildcard path.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.pets.services import MOUNT_BREEDING_COOLDOWN_DAYS, PetService
from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory


def _make_species(slug, name=None):
    return PetSpecies.objects.create(slug=slug, name=name or slug.title())


def _make_potion(slug, name=None, rarity="common"):
    return PotionType.objects.create(slug=slug, name=name or slug.title(), rarity=rarity)


def _make_egg(species):
    return ItemDefinition.objects.create(
        slug=f"{species.slug}-egg",
        name=f"{species.name} Egg",
        icon="🥚",
        item_type=ItemDefinition.ItemType.EGG,
        pet_species=species,
    )


def _make_potion_item(potion):
    return ItemDefinition.objects.create(
        slug=f"potion-{potion.slug}",
        name=f"{potion.name} Potion",
        icon="🧪",
        item_type=ItemDefinition.ItemType.POTION,
        potion_type=potion,
    )


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class BreedMountsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.wolf = _make_species("wolf")
        self.fox = _make_species("fox")
        self.base_potion = _make_potion("base")
        self.fire_potion = _make_potion("fire", rarity="uncommon")
        self.cosmic_potion = _make_potion("cosmic", rarity="legendary")

        # Egg + potion items must exist for the service to grant them.
        _make_egg(self.wolf)
        _make_egg(self.fox)
        _make_potion_item(self.base_potion)
        _make_potion_item(self.fire_potion)
        _make_potion_item(self.cosmic_potion)

        self.mount_a = UserMount.objects.create(
            user=self.user, species=self.wolf, potion=self.base_potion,
        )
        self.mount_b = UserMount.objects.create(
            user=self.user, species=self.fox, potion=self.fire_potion,
        )

    def test_breeding_grants_egg_and_potion_and_sets_cooldown(self):
        with patch("apps.pets.services.random.random", return_value=0.5):
            result = PetService.breed_mounts(
                self.user, self.mount_a.pk, self.mount_b.pk,
            )

        # Exactly one egg of the picked species landed in inventory.
        egg_invs = UserInventory.objects.filter(
            user=self.user, item__item_type=ItemDefinition.ItemType.EGG,
        )
        self.assertEqual(egg_invs.count(), 1)
        egg_species = egg_invs.first().item.pet_species.slug
        self.assertIn(egg_species, {"wolf", "fox"})

        # Exactly one potion of the picked type.
        potion_invs = UserInventory.objects.filter(
            user=self.user, item__item_type=ItemDefinition.ItemType.POTION,
        )
        self.assertEqual(potion_invs.count(), 1)
        self.assertIn(
            potion_invs.first().item.potion_type.slug,
            {"base", "fire"},
        )

        # Both mounts got a cooldown stamp.
        self.mount_a.refresh_from_db()
        self.mount_b.refresh_from_db()
        self.assertIsNotNone(self.mount_a.last_bred_at)
        self.assertIsNotNone(self.mount_b.last_bred_at)

        self.assertFalse(result["chromatic"])

    def test_cannot_breed_mount_with_itself(self):
        with self.assertRaises(ValueError):
            PetService.breed_mounts(self.user, self.mount_a.pk, self.mount_a.pk)

    def test_cooldown_blocks_repeat_breeding(self):
        with patch("apps.pets.services.random.random", return_value=0.5):
            PetService.breed_mounts(self.user, self.mount_a.pk, self.mount_b.pk)

        with self.assertRaises(ValueError):
            PetService.breed_mounts(self.user, self.mount_a.pk, self.mount_b.pk)

    def test_cooldown_expires_after_window(self):
        # Put the cooldown firmly in the past so it has expired.
        past = timezone.now() - timedelta(days=MOUNT_BREEDING_COOLDOWN_DAYS + 1)
        UserMount.objects.filter(pk__in=[self.mount_a.pk, self.mount_b.pk]).update(
            last_bred_at=past,
        )

        with patch("apps.pets.services.random.random", return_value=0.5):
            result = PetService.breed_mounts(
                self.user, self.mount_a.pk, self.mount_b.pk,
            )
        self.assertIn("egg_item_id", result)

    def test_chromatic_upgrade_when_roll_succeeds(self):
        # Force the 1-in-50 chromatic path AND the species/potion choices.
        with patch("apps.pets.services.random.random", return_value=0.001), \
             patch("apps.pets.services.random.choice",
                   side_effect=lambda seq: seq[0]):
            result = PetService.breed_mounts(
                self.user, self.mount_a.pk, self.mount_b.pk,
            )

        self.assertTrue(result["chromatic"])
        self.assertEqual(result["picked_potion"], "Cosmic")
        # Cosmic potion item in inventory.
        self.assertTrue(
            UserInventory.objects.filter(
                user=self.user,
                item__potion_type=self.cosmic_potion,
            ).exists()
        )

    def test_unknown_mount_raises(self):
        other_user = User.objects.create_user(
            username="other", password="pw", role="child",
        )
        other_mount = UserMount.objects.create(
            user=other_user, species=self.wolf, potion=self.base_potion,
        )
        with self.assertRaises(ValueError):
            PetService.breed_mounts(self.user, self.mount_a.pk, other_mount.pk)

    def test_breeding_emits_mount_bred_notification(self):
        """Successful breeding fires a MOUNT_BRED notification on the owner.
        Added in migration 0008 — earlier breeds were silent."""
        from apps.notifications.models import Notification, NotificationType

        with patch("apps.pets.services.random.random", return_value=0.5):
            PetService.breed_mounts(self.user, self.mount_a.pk, self.mount_b.pk)

        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                notification_type=NotificationType.MOUNT_BRED,
            ).exists(),
        )
