"""Prepared Fire/Ice ingredients are usable only after exact art approval."""
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserPet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


ELEMENTAL_POLICY = {
    "schema_version": 1,
    "pets": [
        {"species_slug": slug, "sprite_key": sprite, "potion_slugs": ["base", "fire", "ice"]}
        for slug, sprite in (("chick", "cute-chick"), ("meshtint-wolf", "meshtint-wolf"))
    ],
    "potion_slugs": ["base", "fire", "ice"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
}
NOW = datetime(2026, 10, 20, 18, tzinfo=dt_timezone.utc)


@override_settings(RPG_ASSET_SUPPORT_POLICY=ELEMENTAL_POLICY, PET_INCUBATION_DURATION_SECONDS=86400,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalIncubationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.child = make_family("Elemental incubation", children=[{"username": "element-incubator"}]).children[0]
        cls.species = {slug: PetSpecies.objects.get(slug=slug) for slug in ("chick", "meshtint-wolf")}
        cls.potions = {slug: PotionType.objects.get(slug=slug) for slug in ("base", "fire", "ice")}

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def ingredients(self, species_slug, potion_slug):
        egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
        potion = ItemDefinition.objects.get(slug=f"{potion_slug}-potion")
        for item in (egg, potion):
            UserInventory.objects.get_or_create(user=self.child, item=item, defaults={"quantity": 3})
        return egg, potion

    def start(self, egg, potion):
        return self.client.post("/api/pets/incubations/", {
            "egg_item_id": egg.pk, "potion_item_id": potion.pk, "request_id": str(uuid4()),
        }, format="json")

    def assert_unspent(self, egg, potion):
        for item in (egg, potion):
            self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 3)
        self.assertFalse(PetIncubation.objects.filter(user=self.child).exists())
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())

    def assert_pair_waits_and_hatches(self, species_slug, potion_slug):
        egg, potion = self.ingredients(species_slug, potion_slug)
        with patch("django.utils.timezone.now", return_value=NOW):
            response = self.start(egg, potion)
        self.assertEqual(response.status_code, 201, response.content)
        row = response.json()["incubation"]
        self.assertEqual((row["species"]["slug"], row["potion_type"]["slug"]), (species_slug, potion_slug))
        self.assertEqual(row["remaining_seconds"], 86400)
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())
        claim_url = f"/api/pets/incubations/{row['id']}/hatch/"
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(seconds=86399)):
            self.assertEqual(self.client.post(claim_url, {}, format="json").status_code, 409)
        # A retired art policy cannot revoke an already reserved exact pair.
        with override_settings(RPG_ASSET_SUPPORT_POLICY=None), patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            claimed = self.client.post(claim_url, {}, format="json")
            retry = self.client.post(claim_url, {}, format="json")
        self.assertEqual((claimed.status_code, retry.status_code), (201, 200))
        pet = claimed.json()["pet"]
        self.assertEqual((pet["species"]["slug"], pet["potion"]["slug"]), (species_slug, potion_slug))
        self.assertEqual(pet["lifecycle_stage"], "baby")
        self.assertEqual(pet["growth_points"], 0)
        self.assertEqual(retry.json()["pet"]["id"], pet["id"])
        self.assertFalse(retry.json()["freshly_hatched"])
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 1)
        for item in (egg, potion):
            self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 2)

    def test_fire_chick_waits_then_claims_exact_variant(self):
        self.assert_pair_waits_and_hatches("chick", "fire")

    def test_ice_chick_waits_then_claims_exact_variant(self):
        self.assert_pair_waits_and_hatches("chick", "ice")

    def test_fire_wolf_waits_then_claims_exact_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-wolf", "fire")

    def test_ice_wolf_waits_then_claims_exact_variant(self):
        self.assert_pair_waits_and_hatches("meshtint-wolf", "ice")

    @override_settings(RPG_ASSET_SUPPORT_POLICY=None)
    def test_default_policy_denies_all_four_unprepared_pairs_without_consumption(self):
        for species_slug in self.species:
            for potion_slug in ("fire", "ice"):
                with self.subTest(species=species_slug, potion=potion_slug):
                    egg, potion = self.ingredients(species_slug, potion_slug)
                    self.assertEqual(self.start(egg, potion).status_code, 400)
                    self.assert_unspent(egg, potion)

    def test_canonical_ingredient_rejects_spoofed_slug_fk_or_metadata(self):
        for species_slug in self.species:
            for mutation in ({"slug": "renamed-fire-potion"}, {"potion_type": self.potions["ice"]},
                             {"potion_type": None}, {"metadata": {"variant": "ice"}}):
                with self.subTest(species=species_slug, mutation=mutation):
                    egg, potion = self.ingredients(species_slug, "fire")
                    try:
                        for key, value in mutation.items():
                            setattr(potion, key, value)
                        potion.save(update_fields=list(mutation))
                        self.assertEqual(self.start(egg, potion).status_code, 400)
                        self.assert_unspent(egg, potion)
                    finally:
                        # Keep every subcase independent even on the unfixed
                        # baseline, where a spoof may reserve an incubation.
                        PetIncubation.objects.filter(user=self.child).delete()
                        potion.slug, potion.potion_type = "fire-potion", self.potions["fire"]
                        potion.metadata = {"variant": "fire"}
                        potion.save(update_fields=["slug", "potion_type", "metadata"])
                        UserInventory.objects.filter(user=self.child).update(quantity=3)
