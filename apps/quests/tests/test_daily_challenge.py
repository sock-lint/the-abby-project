"""Tests for the 2026-04-23 daily-challenge feature.

Covers ``DailyChallengeService`` — create/no-dup, record_progress
trigger-matching + hour quantization, and claim idempotency.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

from apps.projects.models import User
from apps.quests.models import DailyChallenge
from apps.quests.services import DailyChallengeService
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class DailyChallengeServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_get_or_create_today_is_idempotent(self):
        first = DailyChallengeService.get_or_create_today(self.user)
        second = DailyChallengeService.get_or_create_today(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            DailyChallenge.objects.filter(user=self.user).count(), 1,
        )

    def test_record_progress_matches_trigger(self):
        # Force a CHORES-type template so chore_complete increments it.
        with patch(
            "apps.quests.services.random.choice",
            return_value={
                "type": DailyChallenge.ChallengeType.CHORES,
                "target": 2, "coins": 10, "xp": 20,
            },
        ):
            DailyChallengeService.get_or_create_today(self.user)

        challenge, newly = DailyChallengeService.record_progress(
            self.user, "chore_complete",
        )
        self.assertEqual(challenge.current_progress, 1)
        self.assertFalse(newly)

        challenge, newly = DailyChallengeService.record_progress(
            self.user, "chore_complete",
        )
        self.assertEqual(challenge.current_progress, 2)
        self.assertTrue(newly)
        self.assertIsNotNone(challenge.completed_at)

    def test_record_progress_ignores_unmatched_triggers(self):
        with patch(
            "apps.quests.services.random.choice",
            return_value={
                "type": DailyChallenge.ChallengeType.CHORES,
                "target": 1, "coins": 10, "xp": 20,
            },
        ):
            DailyChallengeService.get_or_create_today(self.user)

        challenge, newly = DailyChallengeService.record_progress(
            self.user, "habit_log",
        )
        # Challenge exists but wasn't advanced — trigger didn't match type.
        self.assertEqual(challenge.current_progress, 0)
        self.assertFalse(newly)

    def test_clock_hour_quantizes_by_floor_hours(self):
        with patch(
            "apps.quests.services.random.choice",
            return_value={
                "type": DailyChallenge.ChallengeType.CLOCK_HOUR,
                "target": 2, "coins": 15, "xp": 25,
            },
        ):
            DailyChallengeService.get_or_create_today(self.user)

        # 30 minutes doesn't count.
        challenge, _ = DailyChallengeService.record_progress(
            self.user, "clock_out", {"duration_minutes": 30},
        )
        self.assertEqual(challenge.current_progress, 0)

        # 90 minutes is 1 hour.
        challenge, _ = DailyChallengeService.record_progress(
            self.user, "clock_out", {"duration_minutes": 90},
        )
        self.assertEqual(challenge.current_progress, 1)

    def test_claim_raises_if_incomplete(self):
        DailyChallengeService.get_or_create_today(self.user)
        with self.assertRaises(ValueError):
            DailyChallengeService.claim_reward(self.user)

    def test_claim_is_idempotent(self):
        with patch(
            "apps.quests.services.random.choice",
            return_value={
                "type": DailyChallenge.ChallengeType.CHORES,
                "target": 1, "coins": 10, "xp": 20,
            },
        ):
            DailyChallengeService.get_or_create_today(self.user)
        DailyChallengeService.record_progress(self.user, "chore_complete")

        first = DailyChallengeService.claim_reward(self.user)
        self.assertFalse(first["already_claimed"])
        self.assertEqual(first["coins"], 10)

        second = DailyChallengeService.claim_reward(self.user)
        self.assertTrue(second["already_claimed"])
        self.assertEqual(second["coins"], 0)

    def test_claim_coins_are_boosted_by_active_lucky_coin(self):
        """An active Lucky Coin must double the daily challenge coin payout
        (the boost flag was previously masked by the ``adjustment`` reason)."""
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])

        with patch(
            "apps.quests.services.random.choice",
            return_value={
                "type": DailyChallenge.ChallengeType.CHORES,
                "target": 1, "coins": 10, "xp": 20,
            },
        ):
            DailyChallengeService.get_or_create_today(self.user)
        DailyChallengeService.record_progress(self.user, "chore_complete")

        result = DailyChallengeService.claim_reward(self.user)
        self.assertFalse(result["already_claimed"])
        # Service-reported value is the pre-boost amount; the ledger entry
        # written by ``CoinService.award_coins`` is what actually lands.
        entry = (
            CoinLedger.objects
            .filter(user=self.user, reason=CoinLedger.Reason.DAILY_CHALLENGE)
            .first()
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, 20)
