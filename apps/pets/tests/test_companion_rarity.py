"""Acquisition rarity survives hatching and growth, independently of potion art."""
from io import StringIO
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import (
    PetCodexEntrySerializer, PetSpeciesCatalogSerializer, PetSpeciesSerializer,
    UserMountSerializer, UserPetSerializer,
)
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


SUPPORTED_RARITIES = {
    "chick": "common", "meshtint-bee": "common", "meshtint-mushroom": "common",
    "meshtint-potted-plant": "common", "meshtint-sunflower": "common",
    "meshtint-bat": "uncommon", "meshtint-spider": "uncommon",
    "meshtint-snake": "uncommon", "meshtint-hermit-crab": "uncommon",
    "meshtint-blossom": "uncommon", "meshtint-ghost": "rare",
    "meshtint-wolf": "rare", "meshtint-bomb": "rare",
    "meshtint-shadow": "epic", "meshtint-dragon": "legendary",
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CompanionRarityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())
        household = make_family("Rarity", children=[{"username": "rarity-child"}])
        cls.child = household.children[0]
        cls.base = PotionType.objects.get(slug="base")
        # Historical variants are synthetic fixtures, outside the shipped roster.
        cls.cosmic = PotionType.objects.create(slug="cosmic", name="Cosmic", rarity="legendary")

    def test_supported_eggs_and_species_share_deliberate_acquisition_tiers(self):
        eggs = ItemDefinition.objects.filter(
            item_type="egg", pet_species__slug__in=SUPPORTED_RARITIES,
        ).select_related("pet_species")
        self.assertEqual(eggs.count(), 15)
        for egg in eggs:
            with self.subTest(species=egg.pet_species.slug):
                expected = SUPPORTED_RARITIES[egg.pet_species.slug]
                self.assertEqual(egg.rarity, expected)
                self.assertEqual(getattr(egg.pet_species, "rarity", None), expected)

    def test_catalog_and_codex_expose_species_rarity_without_changing_base_potion(self):
        dragon = PetSpecies.objects.get(slug="meshtint-dragon")
        for serializer_class in (PetSpeciesSerializer, PetSpeciesCatalogSerializer, PetCodexEntrySerializer):
            with self.subTest(serializer=serializer_class.__name__):
                data = serializer_class(dragon).data
                self.assertEqual(data.get("rarity"), "legendary")
        self.assertEqual(self.base.rarity, "common")
        self.assertEqual(set(dragon.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
        for serializer_class in (PetSpeciesCatalogSerializer, PetCodexEntrySerializer):
            self.assertEqual({row["slug"] for row in serializer_class(dragon).data["available_potions"]},
                             {"base", "fire", "ice"})

    def test_owned_rarity_follows_species_and_survives_growth_and_evolution(self):
        dragon = PetSpecies.objects.get(slug="meshtint-dragon")
        pet = UserPet.objects.create(user=self.child, species=dragon, potion=self.base)
        self.assertEqual(UserPetSerializer(pet).data.get("rarity"), "legendary")
        pet.growth_points = 100
        pet.evolved_to_mount = True
        pet.save()
        mount = UserMount.objects.create(user=self.child, species=dragon, potion=self.base)
        self.assertEqual(UserPetSerializer(pet).data.get("rarity"), "legendary")
        self.assertEqual(UserMountSerializer(mount).data.get("rarity"), "legendary")

    def test_saved_higher_potion_rarity_is_preserved(self):
        wolf = PetSpecies.objects.create(slug="wolf", name="Wolf", sprite_key="wolf")
        pet = UserPet.objects.create(user=self.child, species=wolf, potion=self.cosmic)
        self.assertEqual(UserPetSerializer(pet).data.get("rarity"), "legendary")
        self.assertFalse(UserPetSerializer(pet).data["catalog_available"])

    def test_rarity_serialization_does_not_query_once_per_pet(self):
        for slug in ("chick", "meshtint-ghost", "meshtint-dragon"):
            UserPet.objects.create(user=self.child, species=PetSpecies.objects.get(slug=slug), potion=self.base)
        pets = UserPet.objects.filter(user=self.child).select_related("species", "potion")
        with self.assertNumQueries(1):
            data = UserPetSerializer(pets, many=True).data
        self.assertEqual({row["rarity"] for row in data}, {"common", "rare", "legendary"})

    def test_migration_backfills_canonical_tiers_without_rewriting_saved_ownership(self):
        legacy = PetSpecies.objects.create(slug="dragon", name="Dragon", sprite_key="dragon")
        ItemDefinition.objects.create(
            slug="dragon-egg", name="Dragon Egg", item_type="egg", pet_species=legacy, rarity="uncommon",
        )
        supported = PetSpecies.objects.get(slug="meshtint-dragon")
        saved = UserPet.objects.create(user=self.child, species=supported, potion=self.base, growth_points=62, name="Spark")
        baseline = UserPet.objects.filter(pk=saved.pk).values().get()
        PetSpecies.objects.filter(pk__in=[legacy.pk, supported.pk]).update(rarity="common")
        ItemDefinition.objects.filter(slug="meshtint-dragon-egg").update(rarity="common")
        migration = import_module("apps.pets.migrations.0009_petspecies_rarity")
        migration.populate_acquisition_rarity(apps, SimpleNamespace(connection=connection))
        legacy.refresh_from_db()
        supported.refresh_from_db()
        self.assertEqual(legacy.rarity, "uncommon")
        self.assertEqual(supported.rarity, "legendary")
        self.assertEqual(ItemDefinition.objects.get(slug="meshtint-dragon-egg").rarity, "legendary")
        self.assertEqual(UserPet.objects.filter(pk=saved.pk).values().get(), baseline)
