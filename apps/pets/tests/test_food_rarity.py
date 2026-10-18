from django.test import TestCase

from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.pets.services import PetService
from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.serializers import ItemDefinitionSerializer


class FoodRarityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="food-rarity", role="child")
        self.species = PetSpecies.objects.create(name="Food test pet", icon="🐤", food_preference="seed")
        self.potion = PotionType.objects.create(name="Food test Base")
        self.pet = UserPet.objects.create(user=self.user, species=self.species, potion=self.potion)

    def food(self, rarity="epic", metadata=None, preferred=False):
        item = ItemDefinition.objects.create(
            name="Test snack", item_type="food", rarity=rarity,
            metadata=metadata if metadata is not None else {"growth": 12},
            food_species=self.species if preferred else None,
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        return item

    def test_epic_neutral_food_honors_authored_growth(self):
        food = self.food()
        result = PetService.feed_pet(self.user, self.pet.pk, food.pk)
        self.assertEqual(result["growth_added"], 12)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 12)

    def test_uncommon_food_keeps_preference_bonus(self):
        food = self.food("uncommon", {"growth": 8}, preferred=True)
        result = PetService.feed_pet(self.user, self.pet.pk, food.pk)
        self.assertEqual(result["growth_added"], 18)

    def test_tonic_doubles_the_whole_food_effect_once(self):
        profile = self.user.character_profile
        profile.pet_growth_boost_remaining = 2
        profile.save()
        food = self.food()
        result = PetService.feed_pet(self.user, self.pet.pk, food.pk)
        self.assertEqual(result["growth_added"], 24)
        profile.refresh_from_db()
        self.assertEqual(profile.pet_growth_boost_remaining, 1)

    def test_invalid_legacy_growth_uses_bounded_rarity_default(self):
        for metadata in ({"growth": -2}, {"growth": True}, {"growth": 1000000}, {"growth": "12"}, {}):
            with self.subTest(metadata=metadata):
                food = self.food("rare", metadata)
                result = PetService.feed_pet(self.user, self.pet.pk, food.pk)
                self.assertEqual(result["growth_added"], 10)

    def test_food_summary_matches_server_growth(self):
        data = ItemDefinitionSerializer(self.food()).data
        self.assertIn("12 growth", data.get("effect_summary", ""))
        self.assertIn("10", data["effect_summary"])

    def test_basic_food_still_gives_five_or_fifteen(self):
        for preferred, expected in ((False, 5), (True, 15)):
            food = self.food("common", {"growth": 2}, preferred=preferred)
            result = PetService.feed_pet(self.user, self.pet.pk, food.pk)
            self.assertEqual(result["growth_added"], expected)
