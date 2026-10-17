"""PostgreSQL regressions for drops overlapping the last owned item's use."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.habits.models import Habit
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, DropService, InventoryItemService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row serialization")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DropInventoryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "Concurrent inventory family", children=[{"username": "inventory-drop-child"}],
        )
        self.child = household.children[0]
        self.habit = Habit.objects.create(
            user=self.child, created_by=self.child, name="Read one page",
            xp_reward=0, max_taps_per_day=1,
        )

    def make_stack(self, *, item_type="consumable", metadata=None):
        item = ItemDefinition.objects.create(
            name="Concurrent drop item", item_type=item_type,
            metadata=metadata or {"effect": "growth_tonic", "feeds": 3},
        )
        UserInventory.objects.create(user=self.child, item=item, quantity=1)
        DropTable.objects.create(trigger_type=TriggerType.HABIT_LOG, item=item, weight=1)
        return item

    def habit_tap(self):
        client = APIClient()
        client.force_authenticate(self.child)
        return client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")

    @staticmethod
    def worker(callback, ready, pids, label):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[label] = cursor.fetchone()[0]
            ready.set()
            return callback()
        finally:
            connection.close()

    def wait_for_overlap(self, future, *, waiting_pid, holder_pid):
        """Observe completion or a real wait on the holder before releasing it."""
        deadline = monotonic() + 4
        tick = Event()
        while monotonic() < deadline:
            if future.done():
                future.result()
                return
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_blocking_pids(%s)", [waiting_pid])
                if holder_pid in cursor.fetchone()[0]:
                    return
            tick.wait(0.01)
        self.fail("Competing operation neither finished nor waited for the held transaction")

    def overlap(self, first, second, held, release):
        """Both operations have their own connection, including after the fix."""
        pids = {}
        first_ready, second_ready = Event(), Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(self.worker, first, first_ready, pids, "first")
            try:
                self.assertTrue(held.wait(5), "First operation did not reach the controlled overlap")
                second_future = pool.submit(self.worker, second, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5), "Competing connection did not start")
                self.wait_for_overlap(
                    second_future, waiting_pid=pids["second"], holder_pid=pids["first"],
                )
            finally:
                release.set()
            return first_future.result(timeout=15), second_future.result(timeout=15)

    def drop_first(self, item, consume):
        drop_read, release_drop = Event(), Event()
        original = QuerySet.get_or_create

        def pause_after_inventory_read(queryset, *args, **kwargs):
            result = original(queryset, *args, **kwargs)
            if queryset.model is UserInventory and kwargs.get("item") == item:
                drop_read.set()
                if not release_drop.wait(10):
                    raise TimeoutError("Drop inventory read was not released")
            return result

        with patch.object(QuerySet, "get_or_create", pause_after_inventory_read):
            with patch("apps.rpg.services.random.random", return_value=0):
                response, used = self.overlap(self.habit_tap, consume, drop_read, release_drop)
        self.assertEqual(response.status_code, 200)
        return response.data["game_event"]["drops"], used

    def assert_saved_drop(self, item, drops):
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]["item_id"], item.pk)
        self.assertEqual(drops[0]["quantity"], 1)
        self.assertFalse(drops[0]["was_salvaged"])
        receipt = DropLog.objects.get(user=self.child, item=item)
        self.assertEqual((receipt.trigger_type, receipt.quantity, receipt.was_salvaged), (
            TriggerType.HABIT_LOG, 1, False,
        ))
        self.assertEqual(
            list(UserInventory.objects.filter(user=self.child, item=item).values_list("quantity", flat=True)),
            [1],
            "The announced drop must remain after consuming the original last unit",
        )

    def assert_one_tonic_used(self, used):
        self.assertEqual(used["quantity_used"], 1)
        self.assertEqual(used["effect"], "growth_tonic")
        self.assertEqual(used["details"], [{"pet_growth_boost_remaining": 3}])
        profile = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(profile.pet_growth_boost_remaining, 3)
        self.assertEqual(profile.consumable_effects_used, ["growth_tonic"])

    def test_habit_drop_read_before_last_consumable_use_preserves_the_grant(self):
        item = self.make_stack()
        drops, used = self.drop_first(item, lambda: ConsumableService.use(self.child, item.pk))

        self.assert_one_tonic_used(used)
        self.assert_saved_drop(item, drops)

    def test_habit_drop_read_before_last_coin_pouch_open_preserves_the_grant(self):
        item = self.make_stack(item_type="coin_pouch", metadata={"coins": 7})
        drops, opened = self.drop_first(
            item, lambda: InventoryItemService.open_coin_pouch(self.child, item.pk),
        )

        self.assertEqual(opened["coins_awarded"], 7)
        credit = CoinLedger.objects.get(user=self.child, description=f"Opened coin pouch: {item.name}")
        self.assertEqual(credit.amount, 7)
        self.assert_saved_drop(item, drops)

    def test_last_consumable_use_before_drop_inventory_read_preserves_the_grant(self):
        item = self.make_stack()
        use_before_delete, release_use = Event(), Event()
        original = UserInventory.delete

        def pause_before_last_stack_delete(inventory, *args, **kwargs):
            if inventory.user_id == self.child.pk and inventory.item_id == item.pk:
                use_before_delete.set()
                if not release_use.wait(10):
                    raise TimeoutError("Last inventory use was not released")
            return original(inventory, *args, **kwargs)

        with patch.object(UserInventory, "delete", pause_before_last_stack_delete):
            with patch("apps.rpg.services.random.random", return_value=0):
                used, drops = self.overlap(
                    lambda: ConsumableService.use(self.child, item.pk),
                    lambda: DropService.process_drops(self.child, TriggerType.HABIT_LOG),
                    use_before_delete, release_use,
                )

        self.assert_one_tonic_used(used)
        self.assert_saved_drop(item, drops)
