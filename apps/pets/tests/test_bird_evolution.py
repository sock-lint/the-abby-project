"""Bird artwork follows saved server growth without adding an ownership tier."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import SkillProgress
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BirdEvolutionTests(TestCase):
    def setUp(self):
        family = make_family("Bird family", children=[
            {"username": "bird-child"}, {"username": "bird-sibling"},
        ])
        self.child, self.sibling = family.children
        self.outsider = make_family("Other birds", children=[
            {"username": "other-bird-child"},
        ]).children[0]
        self.species = PetSpecies.objects.create(
            slug="chick", name="Chick", icon="C", sprite_key="cute-chick",
        )
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.species.available_potions.add(self.base)
        self.pet = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.base,
            name="Pip", growth_points=35, is_active=True,
        )
        self.food = ItemDefinition.objects.create(
            slug="birdseed", name="Birdseed", item_type="food",
            food_species=self.species,
        )
        self.food_inventory = UserInventory.objects.create(
            user=self.child, item=self.food, quantity=6,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def stable(self):
        response = self.client.get("/api/pets/stable/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def feed(self, **extra):
        return self.client.post(f"/api/pets/{self.pet.pk}/feed/", {
            "food_item_id": self.food.pk, **extra,
        }, format="json")

    def test_feed_crosses_fledgling_then_bird_once_and_reloads_the_saved_stage(self):
        self.assertEqual(self.stable()["pets"][0]["evolution_stage"], "chick")

        fledgling = self.feed()

        self.assertEqual(fledgling.status_code, 200)
        self.assertEqual(fledgling.json()["evolution_stage"], "fledgling")
        self.assertFalse(fledgling.json()["evolved"])
        self.assertIsNone(fledgling.json()["mount_id"])
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 50)
        self.assertFalse(self.pet.evolved_to_mount)
        self.assertEqual(self.stable()["pets"][0]["evolution_stage"], "fledgling")
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

        for _ in range(4):
            grown = self.feed()
            self.assertEqual(grown.status_code, 200)
        self.assertEqual(grown.json()["evolution_stage"], "bird")
        self.assertTrue(grown.json()["evolved"])
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 100)
        self.assertTrue(self.pet.evolved_to_mount)
        stable = self.stable()
        self.assertEqual(stable["pets"][0]["evolution_stage"], "bird")
        self.assertEqual(stable["pets"][0]["id"], self.pet.pk)
        self.assertEqual(stable["mounts"][0]["evolution_stage"], "bird")
        self.assertEqual(stable["mounts"][0]["id"], grown.json()["mount_id"])
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 1)
        self.assertEqual(self.feed().status_code, 400)
        self.food_inventory.refresh_from_db()
        self.assertEqual(self.food_inventory.quantity, 1)
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

    def test_stage_boundary_and_reads_never_promote_an_unconfirmed_mount(self):
        for growth, evolved, expected in [
            (0, False, "chick"), (49, False, "chick"),
            (50, False, "fledgling"), (99, False, "fledgling"),
            (100, False, "fledgling"), (100, True, "bird"),
        ]:
            with self.subTest(growth=growth, evolved=evolved):
                UserPet.objects.filter(pk=self.pet.pk).update(
                    growth_points=growth, evolved_to_mount=evolved,
                )
                before = UserPet.objects.values().get(pk=self.pet.pk)
                self.assertEqual(self.stable()["pets"][0]["evolution_stage"], expected)
                self.assertEqual(UserPet.objects.values().get(pk=self.pet.pk), before)
                self.assertFalse(UserMount.objects.filter(user=self.child).exists())

    def test_legacy_species_wrong_art_and_unsupported_potion_keep_their_own_binding(self):
        fire = PotionType.objects.create(slug="fire", name="Fire")
        mount = UserMount.objects.create(user=self.child, species=self.species, potion=self.base)
        for species_slug, sprite_key, potion in [
            ("cat", "cat", self.base),
            ("chick", "other-chick", self.base),
            ("chick", "cute-chick", fire),
        ]:
            with self.subTest(species_slug=species_slug, sprite_key=sprite_key, potion=potion.slug):
                PetSpecies.objects.filter(pk=self.species.pk).update(
                    slug=species_slug, sprite_key=sprite_key,
                )
                UserPet.objects.filter(pk=self.pet.pk).update(potion=potion)
                UserMount.objects.filter(pk=mount.pk).update(potion=potion)
                self.assertIsNone(self.stable()["pets"][0]["evolution_stage"])
                self.assertIsNone(self.stable()["mounts"][0]["evolution_stage"])

    def test_fledgling_activation_preserves_server_stage(self):
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=50, is_active=False)
        response = self.client.post(f"/api/pets/{self.pet.pk}/activate/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evolution_stage"], "fledgling")
        self.assertTrue(response.json()["is_active"])
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 50)
        self.assertFalse(self.pet.evolved_to_mount)

    def test_growth_consumables_derive_stages_from_persisted_growth(self):
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=40)
        feast = ItemDefinition.objects.create(
            slug="bird-feast", name="Bird feast", item_type="consumable",
            metadata={"effect": "feast_platter", "growth": 10},
        )
        UserInventory.objects.create(user=self.child, item=feast)
        ConsumableService.use(self.child, feast.pk)
        self.assertEqual(self.stable()["pets"][0]["evolution_stage"], "fledgling")
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=85)
        surge = ItemDefinition.objects.create(
            slug="bird-surge", name="Bird surge", item_type="consumable",
            metadata={"effect": "growth_surge", "growth": 30},
        )
        UserInventory.objects.create(user=self.child, item=surge)
        ConsumableService.use(self.child, surge.pk)
        stable = self.stable()
        self.assertEqual(stable["pets"][0]["evolution_stage"], "bird")
        self.assertEqual(stable["mounts"][0]["evolution_stage"], "bird")

    def test_forged_stage_cannot_grant_growth_mounts_or_target_another_owner(self):
        response = self.feed(evolution_stage="bird", growth_points=100, evolved_to_mount=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_growth"], 50)
        self.assertEqual(response.json()["evolution_stage"], "fledgling")
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        for owner in (self.sibling, self.outsider):
            pet = UserPet.objects.create(user=owner, species=self.species, potion=self.base)
            rejected = self.client.post(f"/api/pets/{pet.pk}/feed/", {
                "food_item_id": self.food.pk, "evolution_stage": "bird",
            }, format="json")
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(rejected.json(), {"error": "Pet not found"})
            self.assertNotIn(pet.pk, [row["id"] for row in self.stable()["pets"]])
            pet.refresh_from_db()
            self.assertEqual(pet.growth_points, 0)
            self.assertFalse(pet.evolved_to_mount)
