"""Tests for the daily Wellbeing card.

Pinned behaviours:

* ``get_or_create_today`` is idempotent — second call returns the same row,
  same affirmation, no churn.
* The affirmation roll is deterministic per ``(user, date)`` — the YAML
  re-roll is stable across calls.
* First-of-day gratitude submit pays the coin trickle exactly once;
  subsequent same-day edits don't double-pay (verifies via the ledger).
* Validation: empty list rejected, > 3 lines rejected, > 200 chars rejected.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.wellbeing.models import DailyWellbeingEntry
from apps.wellbeing.services import (
    GRATITUDE_FIRST_OF_DAY_COINS,
    MAX_LINE_CHARS,
    WellbeingError,
    WellbeingService,
    _load_affirmations,
    _roll_affirmation_slug,
)


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class WellbeingTodayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        _load_affirmations.cache_clear()

    def test_get_or_create_today_is_idempotent(self):
        first = WellbeingService.get_or_create_today(self.user)
        second = WellbeingService.get_or_create_today(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.affirmation_slug, second.affirmation_slug)
        self.assertEqual(
            DailyWellbeingEntry.objects.filter(user=self.user).count(), 1,
        )

    def test_affirmation_roll_is_deterministic_per_user_per_day(self):
        today = timezone.localdate()
        a = _roll_affirmation_slug(self.user.pk, today)
        b = _roll_affirmation_slug(self.user.pk, today)
        self.assertEqual(a, b)
        # Different day usually rolls different slug; not guaranteed
        # mathematically but the pool is wide enough that consecutive
        # days hashing to the same slug is rare. Just assert the slug
        # roll runs cleanly across multiple days.
        for offset in range(1, 5):
            _roll_affirmation_slug(self.user.pk, today + timedelta(days=offset))

    def test_serialize_today_has_affirmation_text(self):
        entry = WellbeingService.get_or_create_today(self.user)
        payload = WellbeingService.serialize_today(entry)
        self.assertEqual(payload["affirmation"]["slug"], entry.affirmation_slug)
        self.assertGreater(len(payload["affirmation"]["text"]), 0)
        self.assertEqual(payload["gratitude_lines"], [])
        self.assertFalse(payload["gratitude_paid"])


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class GratitudeSubmitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        _load_affirmations.cache_clear()

    def test_first_submit_pays_coin_trickle(self):
        result = WellbeingService.submit_gratitude(
            self.user, ["my dog", "the rain stopped", "warm bread"],
        )
        self.assertTrue(result["freshly_paid"])
        self.assertEqual(result["coin_awarded"], GRATITUDE_FIRST_OF_DAY_COINS)
        ledger = CoinLedger.objects.filter(user=self.user)
        self.assertEqual(ledger.count(), 1)
        entry = ledger.first()
        self.assertEqual(int(entry.amount), GRATITUDE_FIRST_OF_DAY_COINS)
        # ADJUSTMENT — deliberately NOT on the Lucky Coin boost whitelist
        # so the soft-coin trickle stays a flat 2c regardless of consumables.
        self.assertEqual(entry.reason, CoinLedger.Reason.ADJUSTMENT)

    def test_second_submit_same_day_does_not_repay(self):
        WellbeingService.submit_gratitude(self.user, ["one"])
        result = WellbeingService.submit_gratitude(
            self.user, ["one", "two"],
        )
        self.assertFalse(result["freshly_paid"])
        self.assertEqual(result["coin_awarded"], 0)
        # Ledger still has exactly one entry.
        self.assertEqual(CoinLedger.objects.filter(user=self.user).count(), 1)
        # Latest gratitude lines are persisted.
        entry = DailyWellbeingEntry.objects.get(user=self.user)
        self.assertEqual(entry.gratitude_lines, ["one", "two"])

    def test_empty_lines_are_rejected(self):
        with self.assertRaises(WellbeingError):
            WellbeingService.submit_gratitude(self.user, [])
        with self.assertRaises(WellbeingError):
            WellbeingService.submit_gratitude(self.user, ["", "   ", ""])

    def test_too_many_lines_rejected(self):
        with self.assertRaises(WellbeingError):
            WellbeingService.submit_gratitude(
                self.user, ["a", "b", "c", "d"],
            )

    def test_line_length_capped(self):
        with self.assertRaises(WellbeingError):
            WellbeingService.submit_gratitude(
                self.user, ["x" * (MAX_LINE_CHARS + 1)],
            )

    def test_blank_lines_filtered_before_count_check(self):
        # 2 real lines + a blank = passes (the blank is filtered out).
        result = WellbeingService.submit_gratitude(
            self.user, ["one", "  ", "three"],
        )
        entry = DailyWellbeingEntry.objects.get(user=self.user)
        self.assertEqual(entry.gratitude_lines, ["one", "three"])
        self.assertTrue(result["freshly_paid"])
