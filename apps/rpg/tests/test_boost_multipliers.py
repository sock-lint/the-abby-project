"""Tests for the three timer-gated consumable boost multipliers.

Scholar's Draught (xp_boost), Lucky Coin (coin_boost), and Drop Charm
(drop_boost) previously set timer fields on ``CharacterProfile`` without
any code actually reading them — the boosts were cosmetic-only. This
suite pins the expected multiplier behavior end-to-end:

- xp_boost doubles ``AwardService.grant`` XP distributions.
- coin_boost doubles earn-kind ``CoinService.award_coins`` awards.
- drop_boost adds +0.20 to the effective drop rate in
  ``DropService.process_drops``.

Each test verifies both "boost active" AND "boost inactive / lapsed"
paths so a regression (e.g. reading the wrong field, inverting the
timer check) can't silently slip through.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import (
    Badge, ProjectSkillTag, Skill, SkillCategory, SkillProgress,
)
from apps.achievements.services import AwardService
from apps.projects.models import Project, User
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import (
    DropService,
    coin_boost_multiplier,
    drop_boost_additive,
    xp_boost_multiplier,
)


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class BoostHelperTests(TestCase):
    """The three helper functions that read ``CharacterProfile`` timers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

    def test_inactive_returns_1(self):
        self.assertEqual(xp_boost_multiplier(self.user), 1.0)
        self.assertEqual(coin_boost_multiplier(self.user), 1.0)
        self.assertEqual(drop_boost_additive(self.user), 0.0)

    def test_active_xp_boost_returns_2(self):
        self.profile.xp_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["xp_boost_expires_at"])
        self.assertEqual(xp_boost_multiplier(self.user), 2.0)

    def test_lapsed_xp_boost_returns_1(self):
        self.profile.xp_boost_expires_at = timezone.now() - timedelta(minutes=1)
        self.profile.save(update_fields=["xp_boost_expires_at"])
        self.assertEqual(xp_boost_multiplier(self.user), 1.0)

    def test_active_coin_boost_returns_2(self):
        self.profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["coin_boost_expires_at"])
        self.assertEqual(coin_boost_multiplier(self.user), 2.0)

    def test_active_drop_boost_returns_additive(self):
        self.profile.drop_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["drop_boost_expires_at"])
        self.assertEqual(drop_boost_additive(self.user), 0.20)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class CoinBoostIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

    def _activate_coin_boost(self):
        self.profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["coin_boost_expires_at"])

    def test_earn_kind_coins_doubled_when_boost_active(self):
        self._activate_coin_boost()
        entry = CoinService.award_coins(
            self.user, 10, CoinLedger.Reason.HOURLY, description="clock-out",
        )
        self.assertEqual(entry.amount, 20)
        self.assertIn("Lucky Coin", entry.description)

    def test_earn_kind_coins_untouched_when_boost_inactive(self):
        entry = CoinService.award_coins(
            self.user, 10, CoinLedger.Reason.HOURLY,
        )
        self.assertEqual(entry.amount, 10)

    def test_adjustment_coins_not_boosted_even_when_active(self):
        """Check-in bonus, parent manual adjust, salvage all use ADJUSTMENT —
        NONE of them should double. Doubling the check-in would break the
        streak-multiplier design; doubling salvage would double-pay."""
        self._activate_coin_boost()
        entry = CoinService.award_coins(
            self.user, 10, CoinLedger.Reason.ADJUSTMENT,
            description="Daily check-in bonus",
        )
        self.assertEqual(entry.amount, 10)
        self.assertNotIn("Lucky Coin", entry.description)

    def test_redemption_refund_exchange_not_boosted(self):
        """Spend / refund / 1:1 exchange must never be doubled."""
        self._activate_coin_boost()
        for reason in [
            CoinLedger.Reason.REFUND,
            CoinLedger.Reason.EXCHANGE,
        ]:
            entry = CoinService.award_coins(self.user, 10, reason)
            self.assertEqual(
                entry.amount, 10,
                msg=f"{reason} was unexpectedly boosted",
            )

    def test_badge_bonus_doubled_when_boost_active(self):
        """Badge-bonus coins represent earned progression — they do boost."""
        self._activate_coin_boost()
        entry = CoinService.award_coins(
            self.user, 50, CoinLedger.Reason.BADGE_BONUS,
        )
        self.assertEqual(entry.amount, 100)

    def test_chore_reward_doubled_when_boost_active(self):
        self._activate_coin_boost()
        entry = CoinService.award_coins(
            self.user, 25, CoinLedger.Reason.CHORE_REWARD,
        )
        self.assertEqual(entry.amount, 50)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class XpBoostIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        self.category = SkillCategory.objects.create(name="Cooking")
        self.skill = Skill.objects.create(
            name="Baking", category=self.category,
        )
        # Unlock skill so XP actually lands.
        SkillProgress.objects.create(
            user=self.user, skill=self.skill, unlocked=True,
        )
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.project = Project.objects.create(
            title="Bake bread", assigned_to=self.user, created_by=self.parent,
        )
        ProjectSkillTag.objects.create(
            project=self.project, skill=self.skill, xp_weight=1,
        )

    def _activate_xp_boost(self):
        self.profile.xp_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["xp_boost_expires_at"])

    def test_xp_doubled_when_boost_active(self):
        self._activate_xp_boost()
        AwardService.grant(self.user, project=self.project, xp=10)
        sp = SkillProgress.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(sp.xp_points, 20)

    def test_xp_untouched_when_boost_inactive(self):
        AwardService.grant(self.user, project=self.project, xp=10)
        sp = SkillProgress.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(sp.xp_points, 10)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class DropBoostIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        # Single-item drop table so the weighted select is deterministic.
        self.item = ItemDefinition.objects.create(
            slug="test-food", name="Test Food",
            item_type=ItemDefinition.ItemType.FOOD, rarity="common",
        )
        DropTable.objects.create(
            trigger_type="chore_complete", item=self.item, weight=1, min_level=0,
        )

    def _activate_drop_boost(self):
        self.profile.drop_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["drop_boost_expires_at"])

    def test_drop_rate_increases_by_0_20_when_active(self):
        """With chore_complete base 0.30 + boost 0.20 = 0.50, a roll of
        0.45 should drop. Without the boost, base 0.30 means 0.45 should
        not drop. We patch ``random.random`` to land exactly there."""
        self._activate_drop_boost()
        with patch("apps.rpg.services.random.random", return_value=0.45):
            drops = DropService.process_drops(
                self.user, "chore_complete", streak_bonus=0,
            )
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]["item_name"], "Test Food")

    def test_drop_rate_unchanged_when_boost_inactive(self):
        """Same roll 0.45 without boost falls outside base 0.30 — no drop."""
        with patch("apps.rpg.services.random.random", return_value=0.45):
            drops = DropService.process_drops(
                self.user, "chore_complete", streak_bonus=0,
            )
        self.assertEqual(drops, [])
