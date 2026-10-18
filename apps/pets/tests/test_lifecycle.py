"""Every creature family shares a lifecycle without changing saved ownership."""
from io import StringIO
from pathlib import Path
import tempfile
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.mcp_server.shapes import item_definition_to_dict, user_pet_to_dict
from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import (
    PetCodexEntrySerializer, PetSpeciesCatalogSerializer, PetSpeciesSerializer,
    UserMountSerializer,
)
from apps.pets.services import PetService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.serializers import ItemDefinitionSerializer
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


STAGES = ["egg", "baby", "middle", "grown"]


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CompanionLifecycleTests(TestCase):
    def setUp(self):
        family = make_family("Lifecycle family", children=[{"username": "lifecycle-child"}])
        self.child = family.children[0]
        self.other_child = make_family("Other lifecycle family", children=[
            {"username": "other-lifecycle-child"},
        ]).children[0]
        self.species = PetSpecies.objects.create(
            slug="future-fox", name="Future Fox", sprite_key="future-fox", icon="F",
        )
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion,
            growth_points=35, is_active=True,
        )
        self.food = ItemDefinition.objects.create(
            slug="future-fox-food", name="Fox food", item_type="food",
            food_species=self.species,
        )
        UserInventory.objects.create(user=self.child, item=self.food, quantity=10)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def stable(self):
        response = self.client.get("/api/pets/stable/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_saved_growth_and_confirmed_evolution_determine_stage_without_writes(self):
        for growth, evolved, stage in [
            (0, False, "baby"), (49, False, "baby"),
            (50, False, "middle"), (99, False, "middle"),
            (100, False, "middle"), (100, True, "grown"),
        ]:
            with self.subTest(growth=growth, evolved=evolved):
                UserPet.objects.filter(pk=self.pet.pk).update(
                    growth_points=growth, evolved_to_mount=evolved,
                )
                before = UserPet.objects.values().get(pk=self.pet.pk)
                body = self.stable()["pets"][0]
                self.assertEqual(body.get("lifecycle_stage"), stage)
                self.assertEqual(UserPet.objects.values().get(pk=self.pet.pk), before)
                self.assertIsNone(body["evolution_stage"])
                self.assertFalse(UserMount.objects.filter(user=self.child).exists())
                self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_every_saved_family_has_the_same_stages_even_without_current_art(self):
        for slug, sprite in [("future-bat", "future-bat"), ("legacy-wolf", ""), (None, "unknown")]:
            with self.subTest(slug=slug, sprite=sprite):
                PetSpecies.objects.filter(pk=self.species.pk).update(slug=slug, sprite_key=sprite)
                body = self.stable()["pets"][0]
                self.assertEqual(body.get("lifecycle_stage"), "baby")
                self.assertEqual(body["species"].get("lifecycle_stages"), STAGES)
                self.assertFalse(body["catalog_available"])

    def test_mounts_are_grown_and_species_projections_share_the_ordered_lifecycle(self):
        mount = UserMount.objects.create(user=self.child, species=self.species, potion=self.potion)
        self.assertEqual(UserMountSerializer(mount).data.get("lifecycle_stage"), "grown")
        self.species.discovered = True
        self.species.owned_pet_ids = [self.pet.pk]
        self.species.owned_mount_potion_ids = [self.potion.pk]
        for serializer in [PetSpeciesSerializer, PetSpeciesCatalogSerializer, PetCodexEntrySerializer]:
            with self.subTest(serializer=serializer.__name__):
                self.assertEqual(serializer(self.species).data.get("lifecycle_stages"), STAGES)
        self.assertEqual(user_pet_to_dict(self.pet).get("lifecycle_stage"), "baby")

    def test_eggs_keep_their_species_identity_in_rest_and_mcp_inventory(self):
        egg = ItemDefinition.objects.create(
            slug="future-fox-egg", name="Fox Egg", item_type="egg",
            pet_species=self.species, metadata={"species": "wrong-species"},
        )
        UserInventory.objects.create(user=self.child, item=egg, quantity=2)
        inventory = self.client.get("/api/inventory/").json()
        entry = next(row for row in inventory if row["item"]["id"] == egg.pk)
        self.assertEqual(entry["item"].get("lifecycle_stage"), "egg")
        self.assertEqual(entry["item"].get("pet_species_slug"), "future-fox")
        self.assertEqual(entry["quantity"], 2)
        self.assertEqual(entry["available_actions"], [])
        for item in [egg, ItemDefinition.objects.create(
            name="Legacy fox egg", item_type="egg", metadata={"species": "Future Fox"},
        )]:
            with self.subTest(item=item.pk):
                for body in [ItemDefinitionSerializer(item).data, item_definition_to_dict(item)]:
                    self.assertEqual(body.get("lifecycle_stage"), "egg")
                    self.assertEqual(body.get("pet_species_slug"), "future-fox")
        for body in [ItemDefinitionSerializer(self.food).data, item_definition_to_dict(self.food)]:
            self.assertIsNone(body.get("lifecycle_stage"))
            self.assertIsNone(body.get("pet_species_slug"))

    def test_feed_ignores_forged_stage_and_reports_real_middle_then_grown(self):
        response = self.client.post(f"/api/pets/{self.pet.pk}/feed/", {
            "food_item_id": self.food.pk, "lifecycle_stage": "grown", "growth_points": 100,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("lifecycle_stage"), "middle")
        self.assertEqual(response.json()["new_growth"], 50)
        self.assertFalse(response.json()["evolved"])
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        for _ in range(4):
            response = self.client.post(f"/api/pets/{self.pet.pk}/feed/", {
                "food_item_id": self.food.pk,
            }, format="json")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("lifecycle_stage"), "grown")
        self.assertEqual(self.stable()["mounts"][0].get("lifecycle_stage"), "grown")
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_mcp_inventory_exposes_only_owned_egg_stages_with_batched_family_reads(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.schemas import ListInventoryIn
        from apps.mcp_server.tools.inventory import list_inventory

        eggs = [ItemDefinition.objects.create(
            name=f"Bound fox egg {index}", item_type="egg", pet_species=self.species,
        ) for index in range(2)]
        for egg in eggs:
            UserInventory.objects.create(user=self.child, item=egg)
        foreign_egg = ItemDefinition.objects.create(
            name="Other family egg", item_type="egg", pet_species=self.species,
        )
        UserInventory.objects.create(user=self.other_child, item=foreign_egg)
        with override_user(self.child), self.assertNumQueries(1):
            result = list_inventory(ListInventoryIn(item_type="egg"))
        self.assertEqual({row["item"]["id"] for row in result["inventory"]}, {egg.pk for egg in eggs})
        for row in result["inventory"]:
            self.assertEqual(row["item"]["lifecycle_stage"], "egg")
            self.assertEqual(row["item"]["pet_species_slug"], "future-fox")

    def test_stage_spoof_does_not_activate_or_change_another_familys_companion(self):
        other = UserPet.objects.create(
            user=self.other_child, species=self.species, potion=self.potion,
        )
        response = self.client.post(f"/api/pets/{other.pk}/activate/", {
            "lifecycle_stage": "grown", "evolved_to_mount": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertEqual(other.growth_points, 0)
        self.assertFalse(other.is_active)
        self.assertFalse(other.evolved_to_mount)
        self.assertNotIn(other.pk, [pet["id"] for pet in self.stable()["pets"]])

    def test_hatching_consumes_existing_egg_into_a_baby_for_a_new_family(self):
        UserPet.objects.filter(pk=self.pet.pk).delete()
        self.species.available_potions.add(self.potion)
        egg = ItemDefinition.objects.create(
            name="Future Fox Egg", item_type="egg", pet_species=self.species,
        )
        potion = ItemDefinition.objects.create(
            name="Base Potion", item_type="potion", potion_type=self.potion,
        )
        UserInventory.objects.create(user=self.child, item=egg)
        UserInventory.objects.create(user=self.child, item=potion)
        with override_settings(RPG_ASSET_SUPPORT_POLICY={
            "schema_version": 1, "potion_slugs": ["base"],
            "pets": [{"species_slug": "future-fox", "sprite_key": "future-fox", "potion_slugs": ["base"]}],
        }):
            start = self.client.post("/api/pets/incubations/", {
                "egg_item_id": egg.pk, "potion_item_id": potion.pk, "lifecycle_stage": "grown", "request_id": str(uuid4()),
            }, format="json")
        self.assertEqual(start.status_code, 201)
        incubation_id = start.json()["incubation"]["id"]
        PetIncubation.objects.filter(pk=incubation_id).update(ready_at=timezone.now())
        response = self.client.post(f"/api/pets/incubations/{incubation_id}/hatch/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["pet"].get("lifecycle_stage"), "baby")
        self.assertEqual(response.json()["pet"]["growth_points"], 0)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item__in=[egg, potion]).exists())
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 1)
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())

    def test_consumable_and_daily_growth_expose_the_same_middle_and_grown_stages(self):
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=40)
        surge = ItemDefinition.objects.create(
            name="Lifecycle growth", item_type="consumable", metadata={"effect": "growth_surge", "growth": 10},
        )
        UserInventory.objects.create(user=self.child, item=surge)
        result = ConsumableService.use(self.child, surge.pk)
        self.assertEqual(result["details"][0].get("lifecycle_stage"), "middle")
        self.assertEqual(self.stable()["pets"][0].get("lifecycle_stage"), "middle")
        PetSpecies.objects.filter(pk=self.species.pk).update(slug="companion")
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=98)
        result = PetService.auto_grow_companions(self.child)
        self.assertEqual(result["events"][0].get("lifecycle_stage"), "grown")
        self.assertEqual(self.stable()["pets"][0].get("lifecycle_stage"), "grown")

    @override_settings(DEV_TOOLS_ENABLED=True)
    def test_dev_selectors_and_growth_reports_use_the_same_saved_stages(self):
        from apps.accounts.models import User
        from apps.dev_tools.operations import set_pet_growth

        parent = User.objects.create_user(
            username="lifecycle-parent", role="parent", is_staff=True,
            family=self.child.family,
        )
        UserMount.objects.create(user=self.child, species=self.species, potion=self.potion)
        self.client.force_authenticate(parent)
        response = self.client.get("/api/dev/children/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["pets"][0].get("lifecycle_stage"), "baby")
        self.assertEqual(response.json()[0]["mounts"][0].get("lifecycle_stage"), "grown")
        result = set_pet_growth(self.child, pet_id=self.pet.pk, growth=99)
        self.assertEqual(result.get("lifecycle_stage"), "middle")
        self.pet.refresh_from_db()
        self.assertFalse(self.pet.evolved_to_mount)

    def test_all_authored_species_and_namespaced_future_species_have_eggs_and_stages(self):
        from apps.rpg.content.loader import ContentPack

        call_command("loadrpgcontent", stdout=StringIO())
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            (pack / "pet_species.yaml").write_text(
                "species:\n  - slug: axolotl\n    name: Future Axolotl\n    icon: A\n    sprite_key: future-axolotl\n",
                encoding="utf-8",
            )
            ContentPack(pack, namespace="new-").load()
            ContentPack(pack, namespace="new-").load()

        species = PetSpecies.objects.exclude(pk=self.species.pk)
        for family in species:
            with self.subTest(family=family.slug):
                egg = ItemDefinition.objects.get(item_type="egg", pet_species=family)
                body = ItemDefinitionSerializer(egg).data
                self.assertEqual(body.get("lifecycle_stage"), "egg")
                self.assertEqual(body.get("pet_species_slug"), family.slug)
                self.assertEqual(PetSpeciesSerializer(family).data.get("lifecycle_stages"), STAGES)
        future = PetSpecies.objects.get(slug="new-axolotl")
        egg = ItemDefinition.objects.get(pet_species=future, item_type="egg")
        self.assertEqual(egg.slug, "new-axolotl-egg")
        self.assertFalse(ItemDefinitionSerializer(egg).data["catalog_available"])
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 1)
        self.assertEqual(self.stable()["pets"][0]["id"], self.pet.pk)
