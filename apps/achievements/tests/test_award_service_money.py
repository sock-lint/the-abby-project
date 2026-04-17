"""Regression tests for the extended AwardService.grant() signature.

These exercise the paired money + coin path that chore approval and project
completion were refactored to use. If the totals or side effects drift, these
tests catch it before the audit-sensitive ledger behavior diverges.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.achievements.models import Badge, SkillCategory
from apps.achievements.services import AwardService
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, User
from apps.rewards.models import CoinLedger


class AwardServicePairedGrantTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")

    def test_coins_only_grant_creates_no_payment_row(self):
        AwardService.grant(
            self.child,
            coins=20,
            coin_reason=CoinLedger.Reason.ADJUSTMENT,
            coin_description="badge bonus",
        )
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 0)

    def test_money_only_grant_creates_no_coin_row(self):
        AwardService.grant(
            self.child,
            money=Decimal("5.00"),
            money_entry_type=PaymentLedger.EntryType.CHORE_REWARD,
            money_description="test chore",
        )
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 0)

    def test_paired_grant_creates_both_rows(self):
        AwardService.grant(
            self.child,
            coins=15,
            coin_reason=CoinLedger.Reason.CHORE_REWARD,
            coin_description="Chore: Dishes",
            money=Decimal("2.50"),
            money_entry_type=PaymentLedger.EntryType.CHORE_REWARD,
            money_description="Chore: Dishes",
            created_by=self.parent,
        )

        coin_row = CoinLedger.objects.get(user=self.child)
        money_row = PaymentLedger.objects.get(user=self.child)

        self.assertEqual(coin_row.amount, 15)
        self.assertEqual(coin_row.reason, CoinLedger.Reason.CHORE_REWARD)
        self.assertEqual(coin_row.created_by, self.parent)

        self.assertEqual(money_row.amount, Decimal("2.50"))
        self.assertEqual(money_row.entry_type, PaymentLedger.EntryType.CHORE_REWARD)
        self.assertEqual(money_row.created_by, self.parent)

    def test_money_zero_does_not_create_row(self):
        """A project with no bonus_amount shouldn't drop a $0 row."""
        AwardService.grant(
            self.child,
            coins=10,
            coin_reason=CoinLedger.Reason.PROJECT_BONUS,
            coin_description="Project: test",
            money=0,
            money_entry_type=PaymentLedger.EntryType.PROJECT_BONUS,
        )
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_money_description_falls_back_to_coin_description(self):
        AwardService.grant(
            self.child,
            coins=5,
            coin_reason=CoinLedger.Reason.CHORE_REWARD,
            coin_description="Chore: Laundry",
            money=Decimal("1.00"),
            money_entry_type=PaymentLedger.EntryType.CHORE_REWARD,
            # money_description omitted
        )
        money_row = PaymentLedger.objects.get(user=self.child)
        self.assertEqual(money_row.description, "Chore: Laundry")

    def test_project_kwarg_propagates_to_payment_row(self):
        category = SkillCategory.objects.create(name="Test", icon="t")
        project = Project.objects.create(
            title="P", description="D", assigned_to=self.child,
            category=category, created_by=self.parent,
        )
        AwardService.grant(
            self.child,
            project=project,
            coins=5,
            coin_reason=CoinLedger.Reason.PROJECT_BONUS,
            coin_description="x",
            money=Decimal("10.00"),
            money_entry_type=PaymentLedger.EntryType.PROJECT_BONUS,
        )
        money_row = PaymentLedger.objects.get(user=self.child)
        self.assertEqual(money_row.project_id, project.pk)
