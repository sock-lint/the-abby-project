"""Tests for ConsumableService and the Streak Freeze consumable."""
from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, StreakService


def _make_freeze_item():
    return ItemDefinition.objects.create(
        slug="streak-freeze-test",
        name="Streak Freeze",
        icon="❄️",
        item_type=ItemDefinition.ItemType.CONSUMABLE,
        rarity=ItemDefinition.Rarity.RARE,
        coin_value=30,
        metadata={"effect": "streak_freeze", "duration_days": 1},
    )


class ConsumableServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.item = _make_freeze_item()
        UserInventory.objects.create(user=self.user, item=self.item, quantity=1)

    def test_use_streak_freeze_sets_expiry_and_consumes_item(self):
        result = ConsumableService.use(self.user, self.item.pk)
        self.assertEqual(result["effect"], "streak_freeze")

        profile = CharacterProfile.objects.get(user=self.user)
        today = date.today()
        self.assertEqual(profile.streak_freeze_expires_at, today + timedelta(days=1))

        # Quantity was 1 → inventory row should be gone.
        self.assertFalse(
            UserInventory.objects.filter(user=self.user, item=self.item).exists(),
        )

    def test_use_without_inventory_raises(self):
        other_user = User.objects.create_user(username="other", password="pw", role="child")
        with self.assertRaises(ValueError):
            ConsumableService.use(other_user, self.item.pk)

    def test_use_non_consumable_raises(self):
        egg = ItemDefinition.objects.create(
            name="Egg", icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
        )
        UserInventory.objects.create(user=self.user, item=egg, quantity=1)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.user, egg.pk)

    def test_unknown_effect_raises(self):
        item = ItemDefinition.objects.create(
            slug="mystery-consumable",
            name="Mystery",
            icon="?",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "summon_dragon"},
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.user, item.pk)

    def test_decrements_quantity_when_owned_multiple(self):
        # Boost quantity to 3 first.
        inv = UserInventory.objects.get(user=self.user, item=self.item)
        inv.quantity = 3
        inv.save()

        ConsumableService.use(self.user, self.item.pk)

        inv.refresh_from_db()
        self.assertEqual(inv.quantity, 2)


class StreakFreezeIntegrationTests(TestCase):
    """Freeze interacts correctly with StreakService.record_activity gaps."""

    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")

    def test_freeze_preserves_streak_across_one_missed_day(self):
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

        # Day 1: record activity, streak = 1.
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))

        # Arm the freeze before the missed day. Freeze spans day 2.
        profile.refresh_from_db()
        profile.streak_freeze_expires_at = date(2026, 4, 2)
        profile.save()

        # Day 3: user skipped day 2 but the freeze should save them.
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 3))
        self.assertEqual(result["streak"], 2)
        self.assertTrue(result["freeze_consumed"])

        profile.refresh_from_db()
        self.assertIsNone(profile.streak_freeze_expires_at)

    def test_freeze_not_consumed_when_no_gap(self):
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        profile.streak_freeze_expires_at = date(2026, 4, 5)
        profile.save()

        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        self.assertEqual(result["streak"], 1)
        self.assertFalse(result.get("freeze_consumed", False))

        profile.refresh_from_db()
        # Freeze still armed for later use.
        self.assertEqual(profile.streak_freeze_expires_at, date(2026, 4, 5))

    def test_expired_freeze_does_not_save_streak(self):
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))

        profile.refresh_from_db()
        # Freeze expired two days ago — can't protect a gap that happens later.
        profile.streak_freeze_expires_at = date(2026, 4, 1)
        profile.save()

        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 5))
        self.assertEqual(result["streak"], 1)  # Reset because freeze expired.
