"""Future exact-pair contracts run only under scoped synthetic art approval."""
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import UserMountSerializer, UserPetSerializer
from apps.pets.services import PetService
from apps.pets.tests import test_elemental_incubation as incubation_contract
from apps.pets.tests import test_shared_expedition_allowance as expedition_contract
from apps.quests.tests import test_elemental_snake_hermit_crab_preparation as preparation
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(RPG_ASSET_SUPPORT_POLICY=preparation.FUTURE_POLICY,
                   PET_INCUBATION_DURATION_SECONDS=86400,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PreparedSnakeHermitCrabIncubationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        call_command("loadrpgcontent", pack=preparation.PACK, stdout=StringIO())
        cls.child = make_family("Prepared incubation", children=[{"username": "prepared-incubator"}]).children[0]
        cls.foreign = make_family("Foreign incubation", children=[{"username": "foreign-incubator"}]).children[0]

    setUp = incubation_contract.ElementalIncubationTests.setUp
    ingredients = incubation_contract.ElementalIncubationTests.ingredients
    start = incubation_contract.ElementalIncubationTests.start
    assert_unspent = incubation_contract.ElementalIncubationTests.assert_unspent
    assert_pair_waits_and_hatches = incubation_contract.ElementalIncubationTests.assert_pair_waits_and_hatches

    def test_fire_snake_reserves_natural_egg_then_hatches_exact_saved_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-snake", "fire")

    def test_ice_snake_reserves_natural_egg_then_hatches_exact_saved_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-snake", "ice")

    def test_fire_hermit_crab_reserves_natural_egg_then_hatches_exact_saved_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-hermit-crab", "fire")

    def test_ice_hermit_crab_reserves_natural_egg_then_hatches_exact_saved_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-hermit-crab", "ice")

    @override_settings(RPG_ASSET_SUPPORT_POLICY=None)
    def test_production_policy_never_consumes_prepared_elemental_ingredients(self):
        for species in preparation.SPECIES:
            for element in ("fire", "ice"):
                with self.subTest(species=species, potion=element):
                    egg, potion = self.ingredients(species, element)
                    self.assertEqual(self.start(egg, potion).status_code, 400)
                    self.assert_unspent(egg, potion)

    def test_only_owner_can_read_or_claim_reserved_pair_and_pending_slot_is_shared(self):
        egg, potion = self.ingredients("meshtint-snake", "fire")
        with patch("django.utils.timezone.now", return_value=incubation_contract.NOW):
            started = self.start(egg, potion)
            crab_egg, ice = self.ingredients("meshtint-hermit-crab", "ice")
            blocked = self.start(crab_egg, ice, uuid4())
        self.assertEqual(started.status_code, 201)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=crab_egg).quantity, 3)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=ice).quantity, 3)
        foreign_client = APIClient()
        foreign_client.force_authenticate(self.foreign)
        self.assertIsNone(foreign_client.get("/api/pets/incubations/").data["incubation"])
        with patch("django.utils.timezone.now", return_value=incubation_contract.NOW + incubation_contract.timedelta(days=1)):
            denied = foreign_client.post(f"/api/pets/incubations/{started.data['incubation']['id']}/hatch/", {}, format="json")
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(PetIncubation.objects.filter(user=self.child).count(), 1)
        self.assertFalse(UserPet.objects.exists())

    def test_all_appearances_keep_potion_identity_through_baby_middle_and_grown(self):
        food = ItemDefinition.objects.get(slug="food-apple")
        for species_slug in sorted(preparation.SPECIES):
            for potion_slug in ("base", "fire", "ice"):
                with self.subTest(species=species_slug, potion=potion_slug):
                    pet = UserPet.objects.create(user=self.child, species=PetSpecies.objects.get(slug=species_slug),
                        potion=PotionType.objects.get(slug=potion_slug), growth_points=0)
                    self.assertEqual(UserPetSerializer(pet).data["lifecycle_stage"], "baby")
                    pet.growth_points = 49
                    pet.save(update_fields=["growth_points"])
                    UserInventory.objects.update_or_create(user=self.child, item=food, defaults={"quantity": 2})
                    with patch("django.utils.timezone.now", return_value=incubation_contract.NOW):
                        middle = PetService.feed_pet(self.child, pet.pk, food.pk)
                    pet.refresh_from_db()
                    self.assertEqual(middle["lifecycle_stage"], "middle")
                    self.assertEqual(UserPetSerializer(pet).data["potion"]["slug"], potion_slug)
                    pet.growth_points = 99
                    pet.last_fed_at = None
                    pet.save(update_fields=["growth_points", "last_fed_at"])
                    with patch("django.utils.timezone.now", return_value=incubation_contract.NOW):
                        grown = PetService.feed_pet(self.child, pet.pk, food.pk)
                    pet.refresh_from_db()
                    self.assertTrue(grown["evolved"])
                    self.assertTrue(pet.evolved_to_mount)
                    mount = UserMountSerializer(UserMount.objects.get(pk=grown["mount_id"])).data
                    self.assertEqual((mount["species"]["slug"], mount["potion"]["slug"], mount["lifecycle_stage"]),
                        (species_slug, potion_slug, "grown"))


@override_settings(RPG_ASSET_SUPPORT_POLICY=preparation.FUTURE_POLICY)
class PreparedSnakeSharedExpeditionAllowanceTests(expedition_contract.SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-snake", "Snakelet", "meshtint-snake")


@override_settings(RPG_ASSET_SUPPORT_POLICY=preparation.FUTURE_POLICY)
class PreparedHermitCrabSharedExpeditionAllowanceTests(expedition_contract.SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-hermit-crab", "Shell", "meshtint-hermit-crab")


@override_settings(RPG_ASSET_SUPPORT_POLICY=preparation.FUTURE_POLICY)
class PreparedSnakeSharedExpeditionConcurrencyTests(expedition_contract.SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-snake", "Snakelet", "meshtint-snake")


@override_settings(RPG_ASSET_SUPPORT_POLICY=preparation.FUTURE_POLICY)
class PreparedHermitCrabSharedExpeditionConcurrencyTests(expedition_contract.SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-hermit-crab", "Shell", "meshtint-hermit-crab")
