from django.test import TestCase

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.projects.models import User


class PetSpeciesModelTest(TestCase):
    def test_create_species(self):
        species = PetSpecies.objects.create(name="Wolf", icon="🐺", food_preference="meat")
        self.assertEqual(str(species), "🐺 Wolf")


class PotionTypeModelTest(TestCase):
    def test_create_potion(self):
        potion = PotionType.objects.create(name="Fire", color_hex="#FF4500", rarity="uncommon")
        self.assertEqual(str(potion), "Fire")


class UserPetModelTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="petchild", password="test", role="child")
        self.species = PetSpecies.objects.create(name="Wolf", icon="🐺", food_preference="meat")
        self.potion = PotionType.objects.create(name="Fire", color_hex="#FF4500", rarity="uncommon")

    def test_create_pet(self):
        pet = UserPet.objects.create(user=self.child, species=self.species, potion=self.potion)
        self.assertEqual(pet.growth_points, 0)
        self.assertFalse(pet.is_active)
        self.assertFalse(pet.evolved_to_mount)
        self.assertIn("Fire Wolf", str(pet))

    def test_is_fully_grown(self):
        pet = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion, growth_points=100
        )
        self.assertTrue(pet.is_fully_grown)

    def test_unique_together(self):
        UserPet.objects.create(user=self.child, species=self.species, potion=self.potion)
        with self.assertRaises(Exception):
            UserPet.objects.create(user=self.child, species=self.species, potion=self.potion)


class UserMountModelTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="mountchild", password="test", role="child")
        self.species = PetSpecies.objects.create(name="Dragon", icon="🐉")
        self.potion = PotionType.objects.create(name="Ice", color_hex="#87CEEB")

    def test_create_mount(self):
        mount = UserMount.objects.create(
            user=self.child, species=self.species, potion=self.potion
        )
        self.assertFalse(mount.is_active)
        self.assertIn("Mount", str(mount))
