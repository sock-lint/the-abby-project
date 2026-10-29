"""Execute the real PostgreSQL account and catalog serialization boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.pets.models import UserPet
from apps.quests.activity import household_timezone
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family

from apps.egg_discoveries import services
from apps.egg_discoveries.models import DiscoveryActivityCredit, DiscoverySearch, EggDiscovery, PracticeSession
from .factories import ASSET_POLICY, make_catalog


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL account and catalog locks")
@override_settings(
    EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class DiscoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family("Discovery concurrency", children=[{"username": "concurrent-discoverer"}]).children[0]
        self.catalog = make_catalog()
        self.day = timezone.localdate(timezone=household_timezone(self.child))

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
        pids, second_ready = {}, Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(self.worker, first, Event(), pids, "first")
            second_future = None
            try:
                self.assertTrue(held.wait(5), "First operation did not reach its held write")
                second_future = pool.submit(self.worker, second, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5))
                deadline, tick = monotonic() + 4, Event()
                while monotonic() < deadline:
                    if second_future.done():
                        second_future.result()
                        self.fail("Competing operation finished instead of waiting for the held transaction")
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                        if pids["first"] in cursor.fetchone()[0]:
                            break
                    tick.wait(0.01)
                else:
                    self.fail("Competing operation never waited on the held transaction")
            finally:
                release.set()
            return first_future.result(timeout=15), second_future.result(timeout=15)

    def select(self, pair):
        services.select_discovery(self.child, offer_key=pair.key, client_request_id=uuid4())
        return EggDiscovery.objects.get(user=self.child, offer_key=pair.key)

    def credit(self, category, minutes, key):
        return services.credit_activity(self.child, category=category, source_kind="concurrency", source_key=key,
                                        minutes=minutes, occurred_on=self.day)

    def test_concurrent_source_retry_cannot_reroll_or_double_award_guarantee(self):
        for pair in (self.catalog.ordinary, self.catalog.other):
            UserPet.objects.create(user=self.child, species=pair.species, potion=self.catalog.base)
        discovery = self.select(self.catalog.rare)
        self.credit("reading", 150, "reading")
        held, release = Event(), Event()
        original = services._advance

        def hold_first(row):
            held.set()
            if not release.wait(10):
                raise TimeoutError("Credit was not released")
            return original(row)

        with patch.object(services, "_advance", side_effect=hold_first), patch.object(services.random, "random", return_value=0.99) as roll:
            first, replay = self.overlap(lambda: self.credit("movement", 150, "movement"),
                                         lambda: self.credit("movement", 150, "movement"), held, release)
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(roll.call_count, 4)
        self.assertEqual(DiscoverySearch.objects.filter(discovery=discovery).count(), 5)
        self.assertEqual(DiscoveryActivityCredit.objects.count(), 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.rare.egg).quantity, 1)

    def test_concurrent_selects_preserve_both_rows_with_only_one_active(self):
        held, release = Event(), Event()
        original = EggDiscovery.objects.create

        def hold_first(**kwargs):
            if kwargs["offer_key"] == self.catalog.ordinary.key:
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Selection was not released")
            return original(**kwargs)

        with patch.object(EggDiscovery.objects, "create", side_effect=hold_first):
            self.overlap(lambda: self.select(self.catalog.ordinary), lambda: self.select(self.catalog.other), held, release)
        self.assertEqual(EggDiscovery.objects.filter(user=self.child).count(), 2)
        self.assertEqual(EggDiscovery.objects.get(user=self.child, status="active").offer_key, self.catalog.other.key)

    def test_concurrent_practice_uuid_has_one_session_and_credit(self):
        discovery = self.select(self.catalog.ordinary)
        request_id = uuid4()
        held, release = Event(), Event()
        original = services.credit_activity

        def hold_first(*args, **kwargs):
            held.set()
            if not release.wait(10):
                raise TimeoutError("Practice was not released")
            return original(*args, **kwargs)

        with patch.object(services, "credit_activity", side_effect=hold_first):
            fresh, replay = self.overlap(
                lambda: services.log_practice(self.child, name="Drawing", minutes=60, client_request_id=request_id),
                lambda: services.log_practice(self.child, name="Drawing", minutes=60, client_request_id=request_id), held, release,
            )
        self.assertEqual((fresh, replay), (True, False))
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes["practice"], 60)
        self.assertEqual(PracticeSession.objects.count(), 1)
        self.assertEqual(DiscoveryActivityCredit.objects.count(), 1)

    def test_catalog_writer_holds_new_acceptance_without_losing_current_target(self):
        discovery = self.select(self.catalog.ordinary)
        held, release = Event(), Event()

        def writer():
            with transaction.atomic():
                ItemDefinition.objects.filter(pk=self.catalog.other.egg.pk).update(metadata={"species": "changed"})
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Catalog writer was not released")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.worker, writer, Event(), {}, "writer")
            try:
                self.assertTrue(held.wait(5))
                with self.assertRaises(services.DiscoveryConflict):
                    self.select(self.catalog.other)
            finally:
                release.set()
            future.result(timeout=15)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertEqual(EggDiscovery.objects.count(), 1)

    def test_reward_fence_blocks_rebinding_until_the_exact_grant_commits(self):
        discovery = self.select(self.catalog.ordinary)
        self.credit("reading", 150, "reading")
        held, release = Event(), Event()
        original = services.grant_item

        def hold_grant(user, item, quantity):
            if item.pk == self.catalog.ordinary.egg.pk:
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Reward was not released")
            return original(user, item, quantity)

        with patch.object(services, "grant_item", side_effect=hold_grant):
            self.overlap(lambda: self.credit("practice", 90, "practice"),
                         lambda: ItemDefinition.objects.filter(pk=self.catalog.ordinary.egg.pk).update(metadata={"species": "later-change"}), held, release)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "completed")
        self.assertEqual(discovery.reward_receipt["items"][0]["item_id"], self.catalog.ordinary.egg.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.ordinary.egg).quantity, 1)
