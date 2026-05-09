from django.test import TestCase

from apps.pets.models import PetSpecies, PotionType, UserPet, UserMount
from apps.pets.services import PetService
from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory


class PetServiceTestBase(TestCase):
    """Shared setup for PetService tests."""

    def setUp(self):
        self.child = User.objects.create_user(username="petchild", password="test", role="child")
        self.species = PetSpecies.objects.create(name="Wolf", icon="\U0001f43a", food_preference="meat")
        self.potion_type = PotionType.objects.create(name="Fire", color_hex="#FF4500", rarity="uncommon")

        # Item definitions
        self.egg_item = ItemDefinition.objects.create(
            name="Wolf Egg", icon="\U0001f95a", item_type=ItemDefinition.ItemType.EGG,
            rarity="common", metadata={"species": "wolf"},
        )
        self.potion_item = ItemDefinition.objects.create(
            name="Fire Potion", icon="\U0001f9ea", item_type=ItemDefinition.ItemType.POTION,
            rarity="uncommon", metadata={"variant": "fire"},
        )
        self.preferred_food = ItemDefinition.objects.create(
            name="Raw Steak", icon="\U0001f969", item_type=ItemDefinition.ItemType.FOOD,
            rarity="common", metadata={"food_type": "meat"},
        )
        self.neutral_food = ItemDefinition.objects.create(
            name="Berry", icon="\U0001fad0", item_type=ItemDefinition.ItemType.FOOD,
            rarity="common", metadata={"food_type": "fruit"},
        )


class HatchPetTest(PetServiceTestBase):
    def test_hatch_pet(self):
        egg_inv = UserInventory.objects.create(user=self.child, item=self.egg_item, quantity=2)
        potion_inv = UserInventory.objects.create(user=self.child, item=self.potion_item, quantity=1)

        pet = PetService.hatch_pet(self.child, self.egg_item.pk, self.potion_item.pk)

        self.assertEqual(pet.species, self.species)
        self.assertEqual(pet.potion, self.potion_type)
        self.assertEqual(pet.user, self.child)
        self.assertEqual(pet.growth_points, 0)

        # Egg decremented, potion consumed entirely
        egg_inv.refresh_from_db()
        self.assertEqual(egg_inv.quantity, 1)
        self.assertFalse(UserInventory.objects.filter(pk=potion_inv.pk).exists())

    def test_hatch_pet_missing_egg(self):
        # No egg in inventory
        UserInventory.objects.create(user=self.child, item=self.potion_item, quantity=1)
        with self.assertRaises(ValueError):
            PetService.hatch_pet(self.child, self.egg_item.pk, self.potion_item.pk)

    def test_hatch_duplicate_pet(self):
        UserInventory.objects.create(user=self.child, item=self.egg_item, quantity=2)
        UserInventory.objects.create(user=self.child, item=self.potion_item, quantity=2)

        PetService.hatch_pet(self.child, self.egg_item.pk, self.potion_item.pk)
        with self.assertRaises(ValueError):
            PetService.hatch_pet(self.child, self.egg_item.pk, self.potion_item.pk)


class FeedPetTest(PetServiceTestBase):
    def setUp(self):
        super().setUp()
        UserInventory.objects.create(user=self.child, item=self.egg_item, quantity=1)
        UserInventory.objects.create(user=self.child, item=self.potion_item, quantity=1)
        self.pet = PetService.hatch_pet(self.child, self.egg_item.pk, self.potion_item.pk)

    def test_feed_pet_preferred_food(self):
        UserInventory.objects.create(user=self.child, item=self.preferred_food, quantity=1)
        result = PetService.feed_pet(self.child, self.pet.pk, self.preferred_food.pk)

        self.assertEqual(result["growth_added"], 15)
        self.assertEqual(result["new_growth"], 15)
        self.assertFalse(result["evolved"])
        self.assertIsNone(result["mount_id"])

    def test_feed_pet_neutral_food(self):
        UserInventory.objects.create(user=self.child, item=self.neutral_food, quantity=1)
        result = PetService.feed_pet(self.child, self.pet.pk, self.neutral_food.pk)

        self.assertEqual(result["growth_added"], 5)
        self.assertEqual(result["new_growth"], 5)
        self.assertFalse(result["evolved"])

    def test_feed_pet_evolution(self):
        # Set growth near threshold
        self.pet.growth_points = 90
        self.pet.save(update_fields=["growth_points"])

        UserInventory.objects.create(user=self.child, item=self.preferred_food, quantity=1)
        result = PetService.feed_pet(self.child, self.pet.pk, self.preferred_food.pk)

        self.assertTrue(result["evolved"])
        self.assertEqual(result["new_growth"], 100)
        self.assertIsNotNone(result["mount_id"])

        self.pet.refresh_from_db()
        self.assertTrue(self.pet.evolved_to_mount)
        self.assertTrue(UserMount.objects.filter(pk=result["mount_id"]).exists())

    def test_feed_pet_evolution_fires_pet_evolved_notification(self):
        """Cross-the-threshold feeds emit a PET_EVOLVED notification to the
        owner. Added in migration 0008 — before that, evolution was silent."""
        from apps.notifications.models import Notification, NotificationType

        self.pet.growth_points = 90
        self.pet.save(update_fields=["growth_points"])
        UserInventory.objects.create(user=self.child, item=self.preferred_food, quantity=1)

        PetService.feed_pet(self.child, self.pet.pk, self.preferred_food.pk)

        self.assertTrue(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.PET_EVOLVED,
            ).exists(),
            "Expected a PET_EVOLVED notification on the child after evolution.",
        )


class SetActivePetTest(PetServiceTestBase):
    def test_set_active_pet(self):
        species2 = PetSpecies.objects.create(name="Dragon", icon="\U0001f409", food_preference="gems")
        pet1 = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion_type, is_active=True,
        )
        pet2 = UserPet.objects.create(
            user=self.child, species=species2, potion=self.potion_type,
        )

        result = PetService.set_active_pet(self.child, pet2.pk)

        self.assertTrue(result.is_active)
        pet1.refresh_from_db()
        self.assertFalse(pet1.is_active)


class SetActiveMountTest(PetServiceTestBase):
    def test_set_active_mount(self):
        species2 = PetSpecies.objects.create(name="Dragon", icon="\U0001f409")
        mount1 = UserMount.objects.create(
            user=self.child, species=self.species, potion=self.potion_type, is_active=True,
        )
        mount2 = UserMount.objects.create(
            user=self.child, species=species2, potion=self.potion_type,
        )

        result = PetService.set_active_mount(self.child, mount2.pk)

        self.assertTrue(result.is_active)
        mount1.refresh_from_db()
        self.assertFalse(mount1.is_active)
