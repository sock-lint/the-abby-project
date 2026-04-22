"""Tests for the life-RPG consumable effects added on 2026-04-21.

Pins the dispatch branches in ``ConsumableService._apply_effect`` for
``xp_boost`` / ``coin_boost`` / ``drop_boost`` / ``growth_tonic`` /
``rage_breaker``. Streak-freeze has its own test in test_services.py —
this file adds the five new effects plus the ``streak_freezes_used``
counter increment that streak-freeze now maintains.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def _consumable(slug, effect, metadata=None):
    meta = {"effect": effect}
    if metadata:
        meta.update(metadata)
    return ItemDefinition.objects.create(
        slug=slug,
        name=slug,
        item_type=ItemDefinition.ItemType.CONSUMABLE,
        rarity="rare",
        metadata=meta,
    )


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ConsumableEffectsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        # signal auto-creates CharacterProfile on user create, but assert
        # it's there so the test isn't coupled to that ordering.
        CharacterProfile.objects.get_or_create(user=self.user)

    def _give(self, item, qty=1):
        return UserInventory.objects.create(user=self.user, item=item, quantity=qty)

    def test_streak_freeze_sets_expiry_and_increments_counter(self):
        item = _consumable("streak-freeze", "streak_freeze", {"duration_days": 2})
        self._give(item)
        result = ConsumableService.use(self.user, item.pk)

        self.assertIn("streak_freeze_expires_at", result["detail"])
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.streak_freezes_used, 1)
        self.assertEqual(
            profile.streak_freeze_expires_at,
            timezone.localdate() + timedelta(days=2),
        )
        # Consumable decremented to 0 → row deleted.
        self.assertFalse(
            UserInventory.objects.filter(user=self.user, item=item).exists(),
        )

    def test_xp_boost_sets_future_timestamp(self):
        item = _consumable("xp-boost", "xp_boost", {"duration_hours": 24})
        self._give(item)
        before = timezone.now()
        ConsumableService.use(self.user, item.pk)

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertIsNotNone(profile.xp_boost_expires_at)
        delta = profile.xp_boost_expires_at - before
        self.assertGreater(delta, timedelta(hours=23))
        self.assertLess(delta, timedelta(hours=25))

    def test_coin_boost_sets_future_timestamp(self):
        item = _consumable("coin-boost", "coin_boost", {"duration_hours": 12})
        self._give(item)
        ConsumableService.use(self.user, item.pk)

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertIsNotNone(profile.coin_boost_expires_at)
        self.assertGreater(profile.coin_boost_expires_at, timezone.now())

    def test_drop_boost_sets_future_timestamp(self):
        item = _consumable("drop-boost", "drop_boost", {"duration_hours": 48})
        self._give(item)
        ConsumableService.use(self.user, item.pk)

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertIsNotNone(profile.drop_boost_expires_at)

    def test_growth_tonic_increments_remaining_feeds(self):
        item = _consumable("growth-tonic", "growth_tonic", {"feeds": 3})
        self._give(item, qty=2)  # two consumables to stack
        ConsumableService.use(self.user, item.pk)
        ConsumableService.use(self.user, item.pk)

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.pet_growth_boost_remaining, 6)

    def test_rage_breaker_requires_active_boss_quest(self):
        item = _consumable("rage-breaker", "rage_breaker")
        self._give(item)
        with self.assertRaisesRegex(ValueError, "rage shield"):
            ConsumableService.use(self.user, item.pk)

        # Item NOT decremented on the raised error — wrapped in atomic.
        self.assertTrue(
            UserInventory.objects.filter(user=self.user, item=item, quantity=1).exists(),
        )

    def test_rage_breaker_clears_shield_on_active_boss_quest(self):
        from apps.pets.models import PotionType
        from apps.quests.models import Quest, QuestDefinition, QuestParticipant

        # Minimal active boss quest with a non-zero shield.
        definition = QuestDefinition.objects.create(
            name="Testy Boss",
            description="",
            quest_type="boss",
            target_value=100,
        )
        quest = Quest.objects.create(
            definition=definition,
            status=Quest.Status.ACTIVE,
            end_date=timezone.now() + timedelta(days=7),
            rage_shield=60,
        )
        QuestParticipant.objects.create(quest=quest, user=self.user)

        item = _consumable("rage-breaker", "rage_breaker")
        self._give(item)
        result = ConsumableService.use(self.user, item.pk)

        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 0)
        self.assertEqual(result["detail"]["rage_cleared"], 60)

    def test_unknown_effect_raises(self):
        item = _consumable("broken", "xyzzy_unsupported")
        self._give(item)
        with self.assertRaisesRegex(ValueError, "Unknown consumable effect"):
            ConsumableService.use(self.user, item.pk)
