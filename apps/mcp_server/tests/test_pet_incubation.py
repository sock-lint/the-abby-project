"""MCP uses the same accepted incubation and explicit owner-scoped claim as REST."""
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import ClaimPetIncubationIn, GetPetIncubationIn, StartPetIncubationIn
from apps.mcp_server.tools.pets import claim_pet_incubation, get_pet_incubation, start_pet_incubation
from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserPet
from apps.rpg.models import UserInventory, ItemDefinition
from config.tests.factories import make_family


@override_settings(PET_INCUBATION_DURATION_SECONDS=7200, RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PetIncubationToolTests(TestCase):
    def setUp(self):
        family = make_family(parents=[{"username": "incubation-parent"}],
                             children=[{"username": "incubation-child"}, {"username": "incubation-sibling"}])
        self.parent, self.child, self.sibling = family.parents[0], *family.children
        self.other = make_family("Other incubation family", children=[{"username": "other-child"}]).children[0]
        self.species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        self.potion_type = PotionType.objects.create(slug="base", name="Base")
        self.species.available_potions.add(self.potion_type)
        self.egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick Egg", item_type="egg",
                                                  pet_species=self.species, metadata={"species": "chick"})
        self.potion = ItemDefinition.objects.create(slug="base-potion", name="Base Potion", item_type="potion",
                                                     potion_type=self.potion_type, metadata={"variant": "base"})
        for user in (self.child, self.sibling, self.other):
            for item in (self.egg, self.potion):
                UserInventory.objects.create(user=user, item=item, quantity=2)
        self.badge = Badge.objects.create(name="Synthetic first hatch", criteria_type="pets_hatched",
                                          criteria_value={"count": 1}, xp_bonus=0, award_coins=False)

    def saved(self):
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in (PetIncubation, UserInventory, UserPet, UserBadge, ChronicleEntry)}

    def start(self, *, user=None, request_id=None):
        with override_user(user or self.parent):
            return start_pet_incubation(StartPetIncubationIn(
                user_id=self.child.pk, egg_item_id=self.egg.pk, potion_item_id=self.potion.pk,
                request_id=request_id or uuid4(),
            ))

    def test_parent_starts_for_own_child_but_only_a_ready_claim_creates_pet_and_rewards(self):
        request_id = uuid4()
        before_read = self.saved()
        with override_user(self.parent):
            empty = get_pet_incubation(GetPetIncubationIn(user_id=self.child.pk))
        self.assertEqual(empty["incubation"], None)
        self.assertEqual(empty["duration_seconds"], 7200)
        self.assertIn("server_now", empty)
        self.assertEqual(self.saved(), before_read)
        started = self.start(request_id=request_id)
        incubation_id = started["incubation"]["id"]
        self.assertEqual(started["incubation"]["status"], "incubating")
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        after_start = self.saved()
        self.assertEqual(self.start(request_id=request_id)["incubation"]["id"], incubation_id)
        self.assertEqual(self.saved(), after_start)
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                claim_pet_incubation(ClaimPetIncubationIn(user_id=self.child.pk, incubation_id=incubation_id))
        self.assertEqual(self.saved(), after_start)
        PetIncubation.objects.filter(pk=incubation_id).update(ready_at=timezone.now())
        before_ready_read = self.saved()
        with override_user(self.parent):
            ready = get_pet_incubation(GetPetIncubationIn(user_id=self.child.pk))
            self.assertEqual(ready["incubation"]["status"], "ready")
            self.assertEqual(self.saved(), before_ready_read)
            claimed = claim_pet_incubation(ClaimPetIncubationIn(user_id=self.child.pk, incubation_id=incubation_id))
            self.assertTrue(claimed["freshly_hatched"])
            self.assertEqual(claimed["incubation"]["pet_id"], claimed["pet"]["id"])
            self.assertIn("server_now", claimed)
            after_claim = self.saved()
            repeated = claim_pet_incubation(ClaimPetIncubationIn(user_id=self.child.pk, incubation_id=incubation_id))
        self.assertFalse(repeated["freshly_hatched"])
        self.assertEqual(repeated["pet"]["id"], claimed["pet"]["id"])
        self.assertEqual(self.saved(), after_claim)
        replayed_start = self.start(request_id=request_id)
        self.assertEqual(replayed_start["incubation"]["status"], "hatched")
        self.assertEqual(replayed_start["incubation"]["pet_id"], claimed["pet"]["id"])
        self.assertEqual(self.saved(), after_claim)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 1)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=self.badge).count(), 1)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, event_slug="first_pet_hatched").count(), 1)
        self.assertFalse(UserPet.objects.exclude(user=self.child).exists())

    def test_cross_family_target_and_foreign_incubation_ids_are_indistinguishable_from_missing(self):
        incubation_id = self.start()["incubation"]["id"]
        before = self.saved()
        with override_user(self.parent):
            with self.assertRaises(MCPNotFoundError):
                get_pet_incubation(GetPetIncubationIn(user_id=self.other.pk))
            with self.assertRaises(MCPNotFoundError):
                start_pet_incubation(StartPetIncubationIn(user_id=self.other.pk, egg_item_id=self.egg.pk,
                                                          potion_item_id=self.potion.pk, request_id=uuid4()))
        with override_user(self.sibling):
            for incubation in (incubation_id, 999999):
                with self.subTest(incubation=incubation), self.assertRaises(MCPNotFoundError):
                    claim_pet_incubation(ClaimPetIncubationIn(incubation_id=incubation))
            with self.assertRaises(MCPPermissionDenied):
                get_pet_incubation(GetPetIncubationIn(user_id=self.child.pk))
            self.assertIsNone(get_pet_incubation(GetPetIncubationIn())["incubation"])
        self.assertEqual(self.saved(), before)
