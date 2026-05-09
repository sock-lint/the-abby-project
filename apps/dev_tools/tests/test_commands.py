"""Smoke tests for the highest-leverage force commands.

These pin the contract that each command writes through real models in
the right shape — ``DropLog`` row + ``UserInventory`` increment for a
forced drop, ``Notification`` row of the right type for a celebration,
``CharacterProfile.login_streak`` mutation for a streak set, etc. The
goal is to catch regressions where a command silently no-ops because
its target service drifted (the historic Lucky Coin / daily-challenge
shape).

All tests run with ``DEV_TOOLS_ENABLED=True`` since the gate is covered
by ``test_gate.py``.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from config.tests.factories import make_family


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ForceDropTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

        from apps.rpg.models import ItemDefinition

        self.item = ItemDefinition.objects.create(
            slug="dev-test-egg",
            name="Test Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.LEGENDARY,
            coin_value=50,
        )

    def test_force_drop_by_slug_writes_droplog_and_inventory(self):
        from apps.rpg.models import DropLog, UserInventory

        out = StringIO()
        call_command("force_drop", "--user", "abby", "--slug", "dev-test-egg", stdout=out)

        log = DropLog.objects.filter(user=self.child, item=self.item).first()
        self.assertIsNotNone(log)
        self.assertFalse(log.was_salvaged)

        inv = UserInventory.objects.filter(user=self.child, item=self.item).first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.quantity, 1)

    def test_force_drop_count_repeats(self):
        from apps.rpg.models import DropLog, UserInventory

        call_command("force_drop", "--user", "abby", "--slug", "dev-test-egg", "--count", "3")

        self.assertEqual(
            DropLog.objects.filter(user=self.child, item=self.item).count(), 3,
        )
        inv = UserInventory.objects.filter(user=self.child, item=self.item).first()
        self.assertEqual(inv.quantity, 3)

    def test_force_drop_salvage_skips_inventory_credits_coins(self):
        from apps.rewards.models import CoinLedger
        from apps.rpg.models import DropLog, UserInventory

        call_command("force_drop", "--user", "abby", "--slug", "dev-test-egg", "--salvage")

        self.assertFalse(
            UserInventory.objects.filter(user=self.child, item=self.item).exists(),
        )
        log = DropLog.objects.filter(user=self.child, item=self.item).first()
        self.assertTrue(log.was_salvaged)

        ledger = CoinLedger.objects.filter(user=self.child).first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.amount, 50)

    def test_force_drop_by_rarity_picks_from_pool(self):
        # Only one item exists at LEGENDARY, so this should pick it.
        from apps.rpg.models import DropLog

        call_command("force_drop", "--user", "abby", "--rarity", "legendary")

        self.assertTrue(
            DropLog.objects.filter(user=self.child, item=self.item).exists(),
        )


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ForceCelebrationTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_streak_milestone_creates_notification(self):
        from apps.notifications.models import Notification, NotificationType

        call_command(
            "force_celebration", "--user", "abby",
            "--type", "streak_milestone", "--days", "30",
        )

        n = Notification.objects.filter(
            user=self.child,
            notification_type=NotificationType.STREAK_MILESTONE,
        ).first()
        self.assertIsNotNone(n)
        self.assertIn("30", n.title)

    def test_perfect_day_creates_notification(self):
        from apps.notifications.models import Notification, NotificationType

        call_command("force_celebration", "--user", "abby", "--type", "perfect_day")

        self.assertTrue(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.PERFECT_DAY,
            ).exists(),
        )

    def test_birthday_creates_chronicle_entry_with_gift_coins_metadata(self):
        from apps.chronicle.models import ChronicleEntry
        from apps.notifications.models import Notification, NotificationType

        call_command(
            "force_celebration", "--user", "abby",
            "--type", "birthday", "--gift-coins", "1000",
        )

        entry = ChronicleEntry.objects.filter(
            user=self.child, kind=ChronicleEntry.Kind.BIRTHDAY,
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.metadata.get("gift_coins"), 1000)

        n = Notification.objects.filter(
            user=self.child,
            notification_type=NotificationType.BIRTHDAY,
        ).first()
        self.assertIsNotNone(n)
        self.assertIn("1000", n.message)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class SetStreakTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_sets_login_streak_and_last_active_date(self):
        from apps.rpg.models import CharacterProfile

        call_command("set_streak", "--user", "abby", "--days", "29")

        profile = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(profile.login_streak, 29)
        self.assertGreaterEqual(profile.longest_login_streak, 29)
        self.assertEqual(profile.last_active_date, timezone.localdate())

    def test_perfect_days_optional(self):
        from apps.rpg.models import CharacterProfile

        call_command("set_streak", "--user", "abby", "--days", "5", "--perfect-days", "12")

        profile = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(profile.perfect_days_count, 12)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ExpireJournalTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_synthesizes_yesterday_entry_when_none_exists(self):
        from apps.chronicle.models import ChronicleEntry

        call_command("expire_journal", "--user", "abby")

        yesterday = timezone.localdate() - timedelta(days=1)
        entry = ChronicleEntry.objects.filter(
            user=self.child,
            kind=ChronicleEntry.Kind.JOURNAL,
            occurred_on=yesterday,
        ).first()
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_private)

    def test_backdates_existing_today_entry(self):
        from apps.chronicle.models import ChronicleEntry

        today = timezone.localdate()
        chapter_year = today.year if today.month >= 8 else today.year - 1
        existing = ChronicleEntry.objects.create(
            user=self.child,
            kind=ChronicleEntry.Kind.JOURNAL,
            occurred_on=today,
            chapter_year=chapter_year,
            title="Today",
            summary="Body that should survive backdating.",
            is_private=True,
        )

        call_command("expire_journal", "--user", "abby")

        existing.refresh_from_db()
        self.assertEqual(existing.occurred_on, today - timedelta(days=1))
        self.assertEqual(existing.summary, "Body that should survive backdating.")


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ResetDayCountersTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_clears_today_homework_creation_movement_counters(self):
        from apps.creations.models import CreationDailyCounter
        from apps.homework.models import HomeworkDailyCounter
        from apps.movement.models import MovementDailyCounter

        today = timezone.localdate()
        HomeworkDailyCounter.objects.create(user=self.child, occurred_on=today, count=1)
        CreationDailyCounter.objects.create(user=self.child, occurred_on=today, count=2)
        MovementDailyCounter.objects.create(user=self.child, occurred_on=today, count=1)

        call_command("reset_day_counters", "--user", "abby")

        self.assertFalse(HomeworkDailyCounter.objects.filter(user=self.child).exists())
        self.assertFalse(CreationDailyCounter.objects.filter(user=self.child).exists())
        self.assertFalse(MovementDailyCounter.objects.filter(user=self.child).exists())

    def test_kind_filter_isolates_one_counter(self):
        from apps.creations.models import CreationDailyCounter
        from apps.homework.models import HomeworkDailyCounter

        today = timezone.localdate()
        HomeworkDailyCounter.objects.create(user=self.child, occurred_on=today, count=1)
        CreationDailyCounter.objects.create(user=self.child, occurred_on=today, count=2)

        call_command("reset_day_counters", "--user", "abby", "--kind", "homework")

        self.assertFalse(HomeworkDailyCounter.objects.filter(user=self.child).exists())
        # Creation counter untouched.
        self.assertTrue(CreationDailyCounter.objects.filter(user=self.child).exists())


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class SetPetHappinessTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

        from apps.pets.models import PetSpecies, PotionType, UserPet

        self.species = PetSpecies.objects.create(
            slug="testfox", name="Test Fox", icon="🦊", sprite_key="testfox",
        )
        self.potion = PotionType.objects.create(
            slug="testpotion", name="Test Potion",
        )
        self.pet = UserPet.objects.create(
            user=self.child,
            species=self.species,
            potion=self.potion,
            growth_points=10,
            last_fed_at=timezone.now(),
        )

    def test_stale_backdates_last_fed_at_into_band(self):
        from apps.pets.services import happiness_for_pet

        call_command("set_pet_happiness", "--user", "abby", "--level", "stale")

        self.pet.refresh_from_db()
        # Stale band is 8–14 days; we backdate to 8.
        self.assertEqual(happiness_for_pet(self.pet), "stale")

    def test_evolved_pet_excluded(self):
        # The mutator's queryset is filtered to evolved_to_mount=False, so
        # marking the pet evolved should leave nothing to update.
        self.pet.evolved_to_mount = True
        self.pet.save(update_fields=["evolved_to_mount"])

        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("set_pet_happiness", "--user", "abby", "--level", "stale")
