"""Real inventory grants must preserve overlapping grants and last-item use."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.pets.services import PetService
from apps.quests.goals import ingest_activity
from apps.quests.models import (
    ChallengeContribution, ChallengeEnrollment, ChallengeOccurrence,
    QuestDefinition, QuestRewardItem,
)
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, DropService, InventoryItemService
from config.tests.factories import make_family


TEST_POLICY = {
    "schema_version": 1,
    "pets": [
        {"species_slug": slug, "sprite_key": slug, "potion_slugs": ["base"]}
        for slug in ("grant-chick", "grant-fox")
    ],
    "potion_slugs": ["base"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
}


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL inventory row locks")
@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=TEST_POLICY,
)
class InventoryGrantConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family(
            "Inventory grant family", children=[{"username": "inventory-grant-child"}],
        ).children[0]
        self.notify = patch("apps.notifications.services.notify").start()
        self.notify_parents = patch("apps.notifications.services.notify_parents").start()
        self.game_loop = patch("apps.rpg.services.GameLoopService.on_task_completed").start()
        self.addCleanup(patch.stopall)

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

    def overlap(self, first, second, held, release):
        """Release the first transaction after observing completion or a row wait."""
        pids = {}
        first_ready, second_ready = Event(), Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(self.worker, first, first_ready, pids, "first")
            second_future = None
            try:
                self.assertTrue(held.wait(5), "First operation never reached its inventory read")
                second_future = pool.submit(self.worker, second, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5), "Competing connection never started")
                deadline = monotonic() + 4
                tick = Event()
                while monotonic() < deadline:
                    if second_future.done():
                        second_future.result()
                        break
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                        if pids["first"] in cursor.fetchone()[0]:
                            break
                    tick.wait(0.01)
                else:
                    self.fail("Competing operation neither finished nor waited on the held transaction")
            finally:
                release.set()
            first_result = first_future.result(timeout=15)
            self.assertIsNotNone(second_future)
            return first_result, second_future.result(timeout=15)

    def after_inventory_read(self, item, first, second):
        held, release = Event(), Event()
        original = QuerySet.get_or_create

        def pause_first_target_read(queryset, *args, **kwargs):
            result = original(queryset, *args, **kwargs)
            if queryset.model is UserInventory and kwargs.get("item") == item and not held.is_set():
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Held inventory grant was not released")
            return result

        with patch.object(QuerySet, "get_or_create", pause_first_target_read):
            return self.overlap(first, second, held, release)

    def mystery_box(self, *, quantity=1):
        pouch = ItemDefinition.objects.create(
            name="Concurrent coin pouch", item_type="coin_pouch", rarity="common",
            metadata={"coins": 7},
        )
        box = ItemDefinition.objects.create(
            name="Concurrent mystery box", item_type="consumable", rarity="uncommon",
            metadata={"effect": "mystery_box", "rarities": ["common"]},
        )
        UserInventory.objects.create(user=self.child, item=pouch, quantity=1)
        UserInventory.objects.create(user=self.child, item=box, quantity=quantity)
        return box, pouch

    def assert_box_and_pouch_result(self, box, pouch, used, opened):
        self.assertEqual(used["quantity_used"], 1)
        self.assertEqual(used["detail"]["granted_item_id"], pouch.pk)
        self.assertEqual(opened["coins_awarded"], 7)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=box).exists())
        self.assertEqual(
            list(UserInventory.objects.filter(user=self.child, item=pouch).values_list("quantity", flat=True)),
            [1], "The announced mystery-box item must survive opening the original last pouch",
        )
        self.assertEqual(
            list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [7],
        )

    def test_mystery_box_grant_before_last_pouch_open_preserves_new_item(self):
        box, pouch = self.mystery_box()
        with patch("apps.rpg.services.random.choices", return_value=[pouch]):
            used, opened = self.after_inventory_read(
                pouch,
                lambda: ConsumableService.use(self.child, box.pk),
                lambda: InventoryItemService.open_coin_pouch(self.child, pouch.pk),
            )
        self.assert_box_and_pouch_result(box, pouch, used, opened)

    def test_last_pouch_open_before_mystery_box_grant_recreates_stack(self):
        box, pouch = self.mystery_box()
        held, release = Event(), Event()
        original = UserInventory.delete

        def pause_pouch_delete(inventory, *args, **kwargs):
            if inventory.user_id == self.child.pk and inventory.item_id == pouch.pk:
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Held pouch deletion was not released")
            return original(inventory, *args, **kwargs)

        with patch.object(UserInventory, "delete", pause_pouch_delete):
            with patch("apps.rpg.services.random.choices", return_value=[pouch]):
                opened, used = self.overlap(
                    lambda: InventoryItemService.open_coin_pouch(self.child, pouch.pk),
                    lambda: ConsumableService.use(self.child, box.pk), held, release,
                )
        self.assert_box_and_pouch_result(box, pouch, used, opened)

    def make_expedition(self, item):
        species = PetSpecies.objects.create(slug="saved-expedition-bird", name="Saved bird")
        potion = PotionType.objects.create(slug="base", name="Base")
        mount = UserMount.objects.create(user=self.child, species=species, potion=potion)
        return MountExpedition.objects.create(
            mount=mount, tier="short", started_at=timezone.now() - timedelta(hours=3),
            returns_at=timezone.now() - timedelta(seconds=1),
            loot={"coins": 0, "items": [{
                "item_id": item.pk, "quantity": 1, "name": item.name,
                "icon": item.icon, "rarity": item.rarity, "item_type": item.item_type,
            }]},
        )

    def with_drop(self, item, first):
        entry = DropTable.objects.create(trigger_type=TriggerType.HABIT_LOG, item=item, weight=1)
        with patch("apps.rpg.services.random.random", return_value=0):
            with patch("apps.rpg.services.random.choices", return_value=[entry]):
                result, drops = self.after_inventory_read(
                    item, first,
                    lambda: DropService.process_drops(self.child, TriggerType.HABIT_LOG),
                )
        self.assertEqual([(drop["item_id"], drop["quantity"]) for drop in drops], [(item.pk, 1)])
        self.assertEqual(DropLog.objects.filter(user=self.child, item=item, quantity=1).count(), 1)
        self.assertEqual(
            UserInventory.objects.get(user=self.child, item=item).quantity, 3,
            "The original unit, source reward and independently recorded drop must all remain",
        )
        return result

    def test_expedition_claim_preserves_concurrent_drop_and_retry_does_not_duplicate(self):
        food = ItemDefinition.objects.create(name="Expedition food", item_type="food")
        UserInventory.objects.create(user=self.child, item=food, quantity=1)
        expedition = self.make_expedition(food)
        claimed = self.with_drop(food, lambda: ExpeditionService.claim(self.child, expedition.pk))

        self.assertTrue(claimed["freshly_claimed"])
        self.assertEqual([(slot["item_id"], slot["quantity"]) for slot in claimed["items"]], [(food.pk, 1)])
        expedition.refresh_from_db()
        self.assertEqual(expedition.status, MountExpedition.Status.CLAIMED)
        retried = ExpeditionService.claim(self.child, expedition.pk)
        self.assertFalse(retried["freshly_claimed"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=food).quantity, 3)

    def test_breeding_preserves_concurrent_drop_and_sets_cooldown_once(self):
        chick = PetSpecies.objects.create(slug="grant-chick", sprite_key="grant-chick", name="Chick")
        fox = PetSpecies.objects.create(slug="grant-fox", sprite_key="grant-fox", name="Fox")
        potion = PotionType.objects.create(slug="base", name="Base")
        for species in (chick, fox):
            species.available_potions.add(potion)
        mounts = [UserMount.objects.create(user=self.child, species=species, potion=potion) for species in (chick, fox)]
        egg = ItemDefinition.objects.create(name="Breeding egg", item_type="egg", pet_species=chick)
        potion_item = ItemDefinition.objects.create(name="Breeding potion", item_type="potion", potion_type=potion)
        UserInventory.objects.create(user=self.child, item=egg, quantity=1)

        with patch("apps.pets.services.random.choice", side_effect=lambda options: options[0]):
            result = self.with_drop(egg, lambda: PetService.breed_mounts(self.child, mounts[0].pk, mounts[1].pk))

        self.assertEqual((result["egg_item_id"], result["potion_item_id"]), (egg.pk, potion_item.pk))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=potion_item).quantity, 1)
        for mount in mounts:
            mount.refresh_from_db()
            self.assertIsNotNone(mount.last_bred_at)
        with self.assertRaisesMessage(ValueError, "still resting"):
            PetService.breed_mounts(self.child, mounts[0].pk, mounts[1].pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 3)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=potion_item).quantity, 1)

    def make_goal_reward(self):
        food = ItemDefinition.objects.create(name="Challenge food", item_type="food")
        UserInventory.objects.create(user=self.child, item=food, quantity=1)
        ChallengeEnrollment.objects.create(user=self.child, starts_at=timezone.now() - timedelta(hours=1))
        definition = QuestDefinition.objects.create(
            name="One approved chore", description="Reward the recorded work", is_system=True,
            quest_type="collection", target_value=1, duration_days=7,
            trigger_filter={"allowed_triggers": [TriggerType.CHORE_COMPLETE]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=food, quantity=1)

        def complete_goal():
            return ingest_activity(self.child, "chore_complete", "grant-race", TriggerType.CHORE_COMPLETE)

        return food, definition, complete_goal

    def assert_completed_goal(self, food, definition, complete_goal, result):
        self.assertEqual(len(result["goals"]), 1)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.status, "completed")
        self.assertIsNotNone(occurrence.awarded_at)
        self.assertEqual([(row["item_name"], row["quantity"]) for row in occurrence.reward_receipt["items"]], [(food.name, 1)])
        self.assertEqual(ChallengeContribution.objects.filter(occurrence=occurrence).count(), 1)
        self.assertEqual(complete_goal()["goals"], [])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=food).quantity, 3)

    def test_automatic_goal_reward_preserves_concurrent_drop_and_source_retry(self):
        food, definition, complete_goal = self.make_goal_reward()
        result = self.with_drop(food, complete_goal)
        self.assert_completed_goal(food, definition, complete_goal, result)

    def test_drop_before_automatic_goal_inventory_read_does_not_deadlock(self):
        food, definition, complete_goal = self.make_goal_reward()
        entry = DropTable.objects.create(trigger_type=TriggerType.HABIT_LOG, item=food, weight=1)
        with patch("apps.rpg.services.random.random", return_value=0):
            with patch("apps.rpg.services.random.choices", return_value=[entry]):
                drops, result = self.after_inventory_read(
                    food, lambda: DropService.process_drops(self.child, TriggerType.HABIT_LOG),
                    complete_goal,
                )
        self.assertEqual([(drop["item_id"], drop["quantity"]) for drop in drops], [(food.pk, 1)])
        self.assertEqual(DropLog.objects.filter(user=self.child, item=food, quantity=1).count(), 1)
        self.assert_completed_goal(food, definition, complete_goal, result)

    def test_failed_expedition_claim_rolls_back_item_before_retry(self):
        food = ItemDefinition.objects.create(name="Rollback food", item_type="food")
        inventory = UserInventory.objects.create(user=self.child, item=food, quantity=1)
        expedition = self.make_expedition(food)
        with patch.object(MountExpedition, "save", side_effect=RuntimeError("late claim failure")):
            with self.assertRaisesMessage(RuntimeError, "late claim failure"):
                ExpeditionService.claim(self.child, expedition.pk)
        inventory.refresh_from_db()
        expedition.refresh_from_db()
        self.assertEqual(inventory.quantity, 1)
        self.assertEqual(expedition.status, MountExpedition.Status.ACTIVE)
        self.assertIsNone(expedition.claimed_at)
        self.assertTrue(ExpeditionService.claim(self.child, expedition.pk)["freshly_claimed"])
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity, 2)

    def test_failed_second_box_roll_preserves_both_boxes_and_original_stack(self):
        box, pouch = self.mystery_box(quantity=2)
        with patch("apps.rpg.services.random.choices", side_effect=[[pouch], RuntimeError("second roll failed")]):
            with self.assertRaisesMessage(RuntimeError, "second roll failed"):
                ConsumableService.use(self.child, box.pk, quantity=2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=box).quantity, 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
