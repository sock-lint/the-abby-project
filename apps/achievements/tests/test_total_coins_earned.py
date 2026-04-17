"""Tests for the TOTAL_COINS_EARNED badge criterion."""
from __future__ import annotations

from django.test import TestCase

from apps.achievements.criteria import check
from apps.achievements.models import Badge
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService


class TotalCoinsEarnedCriterionTests(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="coinchild", password="pw", role="child")
        self.badge = Badge.objects.create(
            name="Bronze Saver",
            description="Earn 500 coins lifetime",
            criteria_type=Badge.CriteriaType.TOTAL_COINS_EARNED,
            criteria_value={"amount": 500},
        )

    def _grant(self, amount, reason=CoinLedger.Reason.ADJUSTMENT):
        CoinService.award_coins(self.child, amount, reason, description="test")

    def test_under_threshold_returns_false(self):
        self._grant(100)
        self._grant(200)
        self.assertFalse(check(self.child, self.badge))

    def test_at_threshold_returns_true(self):
        self._grant(500)
        self.assertTrue(check(self.child, self.badge))

    def test_sums_multiple_positive_rows(self):
        self._grant(200)
        self._grant(150)
        self._grant(200)
        self.assertTrue(check(self.child, self.badge))  # 550 >= 500

    def test_ignores_negative_rows(self):
        """Spends shouldn't subtract from the lifetime earned total —
        it's a career stat, not a balance."""
        self._grant(500)
        # Spend 400 via redemption (negative)
        CoinLedger.objects.create(
            user=self.child,
            amount=-400,
            reason=CoinLedger.Reason.REDEMPTION,
            description="spent",
        )
        # Still counts as 500 earned lifetime
        self.assertTrue(check(self.child, self.badge))

    def test_other_users_do_not_count(self):
        other = User.objects.create_user(username="other", password="pw", role="child")
        CoinService.award_coins(
            other, 1000, CoinLedger.Reason.ADJUSTMENT, description="other",
        )
        self.assertFalse(check(self.child, self.badge))
