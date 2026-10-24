"""The registered legacy tools retain household locks through native work and serialization."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import OperationalError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.chronicle.models import ChronicleEntry
from apps.families.models import Family
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import chronicle, inventory, pets
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LegacyHouseholdConcurrencyTests(TransactionTestCase):
    def setUp(self):
        home = make_family("Locked legacy household", parents=[{"username": "lock-legacy-parent", "is_staff": True}],
                           children=[{"username": "lock-legacy-child"}])
        self.parent, self.child = home.parents[0], home.children[0]
        self.other = make_family("Next legacy household").family
        self.entry = ChronicleEntry.objects.create(
            user=self.child, kind="journal", title="Original shared reflection", summary="Original prose",
            is_private=False, occurred_on=timezone.localdate(), chapter_year=timezone.localdate().year,
        )
        self.item = ItemDefinition.objects.create(
            slug="lock-growth-tonic", name="Growth Tonic", item_type="consumable",
            metadata={"effect": "growth_tonic", "feeds": 3},
        )
        UserInventory.objects.create(user=self.child, item=self.item, quantity=2)
        CharacterProfile.objects.get_or_create(user=self.child)
        species = PetSpecies.objects.create(slug="lock-pet", name="Saved companion")
        potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(user=self.child, species=species, potion=potion, is_active=False)

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def worker(self, operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
            return operation()
        finally:
            connection.close()

    def assert_held_until_return(self, module, attr, name, params):
        materialized, release = Event(), Event()
        original = getattr(module, attr)

        def held(*args, **kwargs):
            result = original(*args, **kwargs)
            materialized.set()
            if not release.wait(10):
                raise TimeoutError("Response serialization was not released")
            return result

        with patch.object(module, attr, side_effect=held), ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.worker, lambda: self.wire(name, params))
            try:
                self.assertTrue(materialized.wait(5), "Tool did not materialize its result")
                for model, pk in ((Family, self.parent.family_id), (get_user_model(), self.parent.pk),
                                  (get_user_model(), self.child.pk)):
                    with self.subTest(model=model.__name__, pk=pk):
                        with self.assertRaises(OperationalError) as raised:
                            with transaction.atomic():
                                model.objects.select_for_update(no_key=True, nowait=True).get(pk=pk)
                        cause = raised.exception.__cause__
                        self.assertEqual(getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None), "55P03")
            finally:
                release.set()
            payload = request.result(timeout=15)
        self.assertNotIn("error", payload, payload)
        return payload

    def test_consumable_retains_authority_locks_after_native_effect(self):
        payload = self.assert_held_until_return(
            inventory.ConsumableService, "use", "use_consumable",
            {"user_id": self.child.pk, "item_id": self.item.pk},
        )
        self.assertEqual(payload["quantity_used"], 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)

    def test_pet_activation_retains_authority_locks_through_serialization(self):
        payload = self.assert_held_until_return(
            pets, "user_pet_to_dict", "activate_pet", {"user_id": self.child.pk, "pet_id": self.pet.pk},
        )
        self.assertEqual(payload["id"], self.pet.pk)
        self.assertTrue(UserPet.objects.get(pk=self.pet.pk).is_active)

    def test_chronicle_read_blocks_real_family_move_until_prose_is_materialized(self):
        materialized, release = Event(), Event()
        pids = {}
        original = chronicle.chronicle_entry_to_dict

        def held(entry):
            payload = original(entry)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["reader"] = cursor.fetchone()[0]
            materialized.set()
            if not release.wait(10):
                raise TimeoutError("Chronicle reader was not released")
            return payload

        def move():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["mover"] = cursor.fetchone()[0]
            child = get_user_model().objects.get(pk=self.child.pk)
            child.family = self.other
            child.save(update_fields=["family"])

        with patch.object(chronicle, "chronicle_entry_to_dict", side_effect=held), ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(self.worker, lambda: self.wire("list_chronicle_entries", {"user_id": self.child.pk}))
            mover = None
            try:
                self.assertTrue(materialized.wait(5))
                mover = pool.submit(self.worker, move)
                deadline, blocked = monotonic() + 4, False
                while monotonic() < deadline:
                    if mover.done():
                        mover.result()
                        break
                    if "mover" in pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [pids["mover"]])
                            blocked = pids["reader"] in cursor.fetchone()[0]
                        if blocked:
                            break
                    sleep(0.01)
                self.assertTrue(blocked, "Real User.save family move did not wait for Chronicle serialization")
            finally:
                release.set()
            payload = reader.result(timeout=15)
            if mover is not None:
                mover.result(timeout=15)
        self.assertEqual(payload["entries"][0]["summary"], "Original prose")
        self.assertEqual(self.wire("list_chronicle_entries", {"user_id": self.child.pk})["error"]["code"], "not_found")
