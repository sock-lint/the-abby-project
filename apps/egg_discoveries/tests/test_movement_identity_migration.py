"""Metadata-only upgrade retention never turns old movement into new effort."""
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.movement.models import MovementSession, MovementType
from apps.quests.activity import household_timezone
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, UserInventory
from config.tests.factories import make_family

from apps.egg_discoveries.models import DiscoveryActivityCredit, DiscoverySearch, EggDiscovery
from apps.egg_discoveries.services import credit_activity, select_discovery
from .factories import ASSET_POLICY, make_catalog


@override_settings(
    EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class MovementIdentityMigrationTests(TestCase):
    def test_upgrade_retains_live_uuids_as_zero_credit_and_preserves_existing_receipts(self):
        child = make_family("Movement upgrade", children=[{"username": "movement-upgrade-child"}]).children[0]
        catalog = make_catalog()
        day = timezone.localdate(timezone=household_timezone(child))
        select_discovery(child, offer_key=catalog.ordinary.key, client_request_id=uuid4())
        movement_type = MovementType.objects.create(name="Upgrade walking", slug="upgrade-walking")
        old_id, credited_id = uuid4(), uuid4()
        for request_id, minutes in ((old_id, 55), (credited_id, 60), (None, 90)):
            MovementSession.objects.create(user=child, movement_type=movement_type, duration_minutes=minutes,
                                           occurred_on=day, client_request_id=request_id)
        earned = credit_activity(child, category="movement", source_kind="movement_session", source_key=str(credited_id),
                                 minutes=60, occurred_on=day)
        migration = import_module("apps.egg_discoveries.migrations.0002_preserve_movement_request_identities")
        for _ in range(2):
            migration.preserve_existing_request_identities(apps, SimpleNamespace(connection=connection))
        old = DiscoveryActivityCredit.objects.get(user=child, source_key=str(old_id))
        self.assertEqual((old.minutes, old.credited_minutes, old.occurred_on, old.discovery_id), (55, 0, day, None))
        self.assertEqual(DiscoveryActivityCredit.objects.count(), 2)
        earned.refresh_from_db()
        self.assertEqual(earned.credited_minutes, 60)
        self.assertIsNotNone(earned.discovery_id)
        replay = credit_activity(child, category="movement", source_kind="movement_session", source_key=str(old_id),
                                 minutes=55, occurred_on=day)
        self.assertEqual(replay.pk, old.pk)
        discovery = EggDiscovery.objects.get(user=child)
        self.assertEqual(discovery.minutes, {"reading": 0, "movement": 60, "practice": 0})
        self.assertEqual(discovery.status, "active")
        self.assertFalse(DiscoverySearch.objects.exists())
        self.assertFalse(UserInventory.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())
