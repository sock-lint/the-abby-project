"""Accepted eggs wait for the server deadline, then hatch once on explicit claim."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.notifications.models import Notification
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None, PET_INCUBATION_DURATION_SECONDS=7200,
    COINS_PER_BADGE_RARITY={"common": 7},
)
class PetIncubationTests(TestCase):
    def setUp(self):
        family = make_family("Incubation", children=[
            {"username": "incubator"}, {"username": "incubator-sibling"},
        ])
        self.child, self.sibling = family.children
        self.other = make_family("Other incubator", children=[{"username": "other-incubator"}]).children[0]
        self.species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick", icon="C")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.species.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(
            slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=self.species,
            metadata={"species": "chick"},
        )
        self.potion = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion", potion_type=self.base,
            metadata={"variant": "base"},
        )
        for item in (self.egg, self.potion):
            UserInventory.objects.create(user=self.child, item=item, quantity=3)
        self.badge = Badge.objects.create(name="Incubation first hatch", criteria_type="pets_hatched", criteria_value={"count": 1})
        self.now = datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc)
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.request_id = str(uuid4())

    def start(self, **overrides):
        return self.client.post("/api/pets/incubations/", {
            "egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk,
            "request_id": self.request_id, **overrides,
        }, format="json")

    def start_at(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            response = self.start()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["incubation"]

    def claim(self, row):
        return self.client.post(f"/api/pets/incubations/{row['id']}/hatch/", {}, format="json")

    def assert_no_hatch(self):
        self.assertFalse(UserPet.objects.exists())
        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(Notification.objects.filter(notification_type="badge_earned").exists())
        self.assertFalse(ChronicleEntry.objects.filter(event_slug="first_pet_hatched").exists())

    def quantities(self):
        return list(UserInventory.objects.filter(user=self.child).order_by("item_id").values_list("quantity", flat=True))

    def test_start_consumes_one_pair_without_ownership_growth_or_badges(self):
        row = self.start_at()
        self.assertEqual(self.quantities(), [2, 2])
        self.assertEqual(row["status"], "incubating")
        self.assertEqual(row["remaining_seconds"], 7200)
        self.assertFalse(row["is_ready"])
        self.assertEqual(row["egg"]["id"], self.egg.pk)
        self.assertEqual(row["species"]["slug"], "chick")
        self.assertEqual(row["potion_type"]["slug"], "base")
        self.assertIsNone(row["pet_id"])
        self.assert_no_hatch()

    def test_client_timestamps_and_account_cannot_shorten_or_transfer_incubation(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            response = self.start(user_id=self.sibling.pk, ready_at="2000-01-01T00:00:00Z", duration_seconds=0)
        self.assertEqual(response.status_code, 201)
        row = response.json()["incubation"]
        self.assertEqual(row["remaining_seconds"], 7200)
        self.assertEqual(datetime.fromisoformat(response.json()["server_now"]), self.now)
        self.assertEqual(apps.get_model("pets", "PetIncubation").objects.get(pk=row["id"]).user_id, self.child.pk)
        self.assert_no_hatch()

    def test_failed_reservation_rolls_back_both_consumed_inventory_rows(self):
        with patch("apps.pets.models.PetIncubation.objects.create", side_effect=RuntimeError("synthetic reservation failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic reservation failure"):
                self.start()
        self.assertEqual(self.quantities(), [3, 3])
        self.assertFalse(apps.get_model("pets", "PetIncubation").objects.exists())
        self.assert_no_hatch()

    def test_deadline_is_frozen_server_state_and_get_never_hatches(self):
        self.start_at()
        with override_settings(PET_INCUBATION_DURATION_SECONDS=30), patch("django.utils.timezone.now", return_value=self.now + timedelta(seconds=7199.1)):
            response = self.client.get("/api/pets/incubations/")
        self.assertEqual(response.status_code, 200)
        row = response.json()["incubation"]
        self.assertEqual(row["remaining_seconds"], 1)
        self.assertFalse(row["is_ready"])
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=3)):
            response = self.client.get("/api/pets/incubations/")
        self.assertTrue(response.json()["incubation"]["is_ready"])
        self.assertEqual(response.json()["incubation"]["status"], "ready")
        self.assert_no_hatch()

    def test_early_claim_conflicts_without_consumption_or_rewards(self):
        row = self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(seconds=7199)):
            response = self.claim(row)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.quantities(), [2, 2])
        self.assert_no_hatch()

    def test_ready_claim_and_retry_return_same_baby_and_award_once(self):
        row = self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            response, retry = self.claim(row), self.claim(row)
        self.assertEqual((response.status_code, retry.status_code), (201, 200))
        body, replay = response.json(), retry.json()
        self.assertTrue(body["freshly_hatched"])
        self.assertFalse(replay["freshly_hatched"])
        self.assertEqual(body["pet"]["id"], replay["pet"]["id"])
        self.assertEqual(body["pet"]["growth_points"], 0)
        self.assertEqual(UserPet.objects.count(), 1)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=self.badge).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.child, notification_type="badge_earned").count(), 1)
        self.assertEqual(self.quantities(), [2, 2])
        self.assertIsNone(self.client.get("/api/pets/incubations/").json()["incubation"])

    def test_start_retry_uses_saved_request_before_inventory_validation(self):
        row = self.start_at()
        UserInventory.objects.filter(user=self.child).delete()
        retry = self.start()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["incubation"]["id"], row["id"])
        self.assert_no_hatch()

    def test_start_uuid_remains_idempotent_after_hatching_and_cannot_change_pair(self):
        row = self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            self.assertEqual(self.claim(row).status_code, 201)
        retry = self.start()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["incubation"]["id"], row["id"])
        self.assertEqual(self.start(egg_item_id=self.potion.pk).status_code, 409)
        self.assertEqual(self.quantities(), [2, 2])

    def test_invalid_input_and_owned_pair_do_not_spend_ingredients(self):
        for body in ({"request_id": "invalid"}, {"egg_item_id": 1.5}, {"egg_item_id": True}, {"potion_item_id": 9999}):
            self.assertEqual(self.start(**body).status_code, 400)
        UserPet.objects.create(user=self.child, species=self.species, potion=self.base, growth_points=100, evolved_to_mount=True)
        self.assertEqual(self.start().status_code, 400)
        self.assertEqual(self.quantities(), [3, 3])
        self.assertFalse(apps.get_model("pets", "PetIncubation").objects.exists())

    def test_persisted_unfinished_constraint_and_account_deletion_preserve_catalog(self):
        row = self.start_at()
        model = apps.get_model("pets", "PetIncubation")
        original = model.objects.get(pk=row["id"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(user=self.child, request_id=uuid4(), species=self.species, potion_type=self.base,
                accepted_pair=original.accepted_pair, started_at=original.started_at, ready_at=original.ready_at)
        self.child.delete()
        self.assertFalse(model.objects.exists())
        self.assertTrue(PetSpecies.objects.filter(pk=self.species.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())

    def test_completed_tombstone_never_recreates_a_deleted_pet(self):
        row = self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            self.assertEqual(self.claim(row).status_code, 201)
            UserPet.objects.get().delete()
            self.assertEqual(self.claim(row).status_code, 409)
        self.assertFalse(UserPet.objects.exists())
        self.assertEqual(self.quantities(), [2, 2])

    def test_another_request_cannot_replace_an_unfinished_or_ready_egg(self):
        self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            response = self.start(request_id=str(uuid4()))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.quantities(), [2, 2])
        self.assert_no_hatch()

    def test_accepted_pair_hatches_after_catalog_and_compatibility_retirement(self):
        row = self.start_at()
        fire = PotionType.objects.create(slug="fire", name="Fire")
        self.species.available_potions.set([fire])
        self.species.name = "Retired name"
        self.species.save(update_fields=["name"])
        with patch("apps.pets.services.pet_is_available", return_value=False), patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            response = self.claim(row)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["incubation"]["species"]["name"], "Chick")
        self.assertEqual(UserPet.objects.get().species_id, self.species.pk)

    def test_reserved_ingredient_deletion_keeps_frozen_identities_and_ready_promise(self):
        row = self.start_at()
        self.egg.delete()
        self.potion.delete()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            response = self.claim(row)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["incubation"]["egg"], row["egg"])
        self.assertEqual(response.json()["incubation"]["potion"], row["potion"])

    def test_owner_scoping_hides_sibling_other_family_and_unknown_claims(self):
        row = self.start_at()
        for owner in (self.sibling, self.other):
            self.client.force_authenticate(owner)
            self.assertIsNone(self.client.get("/api/pets/incubations/").json()["incubation"])
            self.assertEqual(self.claim(row).status_code, 404)
        self.assert_no_hatch()
        self.client.force_authenticate(self.child)
        self.assertEqual(self.claim({"id": row["id"] + 1000}).status_code, 404)

    def test_missing_current_returns_configured_duration_and_requires_auth(self):
        with override_settings(PET_INCUBATION_DURATION_SECONDS=900):
            response = self.client.get("/api/pets/incubations/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["incubation"])
        self.assertEqual(response.json()["duration_seconds"], 900)
        self.assertIn("server_now", response.json())
        self.client.force_authenticate(None)
        for method, path in (("get", "/api/pets/incubations/"), ("post", "/api/pets/incubations/"), ("post", "/api/pets/incubations/1/hatch/"), ("post", "/api/pets/hatch/")):
            self.assertIn(getattr(self.client, method)(path).status_code, (401, 403))

    def test_legacy_hatch_cannot_skip_incubation(self):
        response = self.client.post("/api/pets/hatch/", {"egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk}, format="json")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json(), {"error": "Instant hatching has been removed. Start an egg incubation in the Hatchery."})
        self.assertEqual(self.quantities(), [3, 3])
        self.assert_no_hatch()

    def test_payout_failure_rolls_back_hatch_but_preserves_reserved_egg_for_retry(self):
        row = self.start_at()
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)), patch("apps.achievements.services.BadgeService.evaluate_badges", side_effect=RuntimeError("synthetic payout failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic payout failure"):
                self.claim(row)
        self.assert_no_hatch()
        model = apps.get_model("pets", "PetIncubation")
        self.assertIsNone(model.objects.get(pk=row["id"]).hatched_at)
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            self.assertEqual(self.claim(row).status_code, 201)
        self.assertEqual(self.quantities(), [2, 2])
