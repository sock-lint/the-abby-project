"""Tests for ChoreService — is_active_this_week, submit, approve/reject."""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreNotAvailableError, ChoreService
from apps.payments.models import PaymentLedger
from apps.projects.models import User
from apps.rewards.models import CoinLedger


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.child2 = User.objects.create_user(username="c2", password="pw", role="child")


class IsActiveThisWeekTests(_Fixture):
    def test_every_week_always_active(self):
        chore = Chore.objects.create(
            title="Dishes", reward_amount=Decimal("1.00"),
            week_schedule=Chore.WeekSchedule.EVERY_WEEK, created_by=self.parent,
        )
        self.assertTrue(ChoreService.is_active_this_week(chore))

    def test_alternating_without_start_date_defaults_active(self):
        """No schedule_start_date = treat as always active (defensive default)."""
        chore = Chore.objects.create(
            title="Yard", reward_amount=Decimal("1.00"),
            week_schedule=Chore.WeekSchedule.ALTERNATING, created_by=self.parent,
        )
        self.assertTrue(ChoreService.is_active_this_week(chore))

    def test_alternating_matches_parity(self):
        today = datetime.date(2026, 4, 15)  # Wednesday, ISO week 16 (even)
        chore = Chore.objects.create(
            title="Y", reward_amount=Decimal("1.00"),
            week_schedule=Chore.WeekSchedule.ALTERNATING,
            schedule_start_date=today, created_by=self.parent,
        )
        # Same week → active.
        self.assertTrue(ChoreService.is_active_this_week(chore, today))
        # +1 week → opposite parity → inactive.
        next_week = today + datetime.timedelta(days=7)
        self.assertFalse(ChoreService.is_active_this_week(chore, next_week))
        # +2 weeks → same parity → active.
        two_weeks_later = today + datetime.timedelta(days=14)
        self.assertTrue(ChoreService.is_active_this_week(chore, two_weeks_later))


class SubmitCompletionTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("2.00"), coin_reward=5,
            recurrence=Chore.Recurrence.DAILY, created_by=self.parent,
        )

    def test_child_can_submit(self):
        completion = ChoreService.submit_completion(self.child, self.chore)
        self.assertEqual(completion.status, ChoreCompletion.Status.PENDING)
        self.assertEqual(completion.reward_amount_snapshot, Decimal("2.00"))
        self.assertEqual(completion.coin_reward_snapshot, 5)

    def test_parent_cannot_submit(self):
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.parent, self.chore)

    def test_inactive_chore_rejected(self):
        self.chore.is_active = False
        self.chore.save()
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, self.chore)

    def test_assigned_to_other_child_rejected(self):
        self.chore.assigned_to = self.child2
        self.chore.save()
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, self.chore)

    def test_duplicate_same_day_blocked(self):
        ChoreService.submit_completion(self.child, self.chore)
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, self.chore)

    def test_one_time_chore_only_once(self):
        one_time = Chore.objects.create(
            title="Box setup", recurrence=Chore.Recurrence.ONE_TIME,
            reward_amount=Decimal("10"), created_by=self.parent,
        )
        completion = ChoreService.submit_completion(self.child, one_time)
        ChoreService.approve_completion(completion, self.parent)
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, one_time)

    def test_weekly_period_date_is_monday(self):
        weekly = Chore.objects.create(
            title="Vacuum", recurrence=Chore.Recurrence.WEEKLY,
            reward_amount=Decimal("5"), created_by=self.parent,
        )
        completion = ChoreService.submit_completion(self.child, weekly)
        # period date = Monday of current week.
        today = timezone.localdate()
        monday = today - datetime.timedelta(days=today.weekday())
        self.assertEqual(completion.completed_date, monday)


class ApprovalTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("2.00"), coin_reward=5,
            created_by=self.parent,
        )
        self.completion = ChoreService.submit_completion(self.child, self.chore)

    def test_approve_posts_payment_and_coin(self):
        ChoreService.approve_completion(self.completion, self.parent)
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, ChoreCompletion.Status.APPROVED)
        self.assertEqual(self.completion.decided_by, self.parent)
        self.assertIsNotNone(self.completion.decided_at)

        self.assertTrue(PaymentLedger.objects.filter(
            user=self.child, entry_type="chore_reward",
        ).exists())
        self.assertTrue(CoinLedger.objects.filter(
            user=self.child, reason=CoinLedger.Reason.CHORE_REWARD,
        ).exists())

    def test_reject_does_not_post_ledger(self):
        ChoreService.reject_completion(self.completion, self.parent)
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, ChoreCompletion.Status.REJECTED)
        self.assertFalse(PaymentLedger.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(
            user=self.child, reason=CoinLedger.Reason.CHORE_REWARD,
        ).exists())

    def test_approving_already_approved_is_noop(self):
        ChoreService.approve_completion(self.completion, self.parent)
        ChoreService.approve_completion(self.completion, self.parent)
        # Only one ledger row written.
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 1)

    def test_approve_with_stale_in_memory_status_is_noop(self):
        """Race-guard regression: if another worker has already approved
        the row but the current request is holding a stale in-memory
        instance still showing PENDING, ``approve_completion`` must not
        double-pay. The ``select_for_update`` re-fetch closes that gap.
        """
        # Worker A approved already.
        ChoreService.approve_completion(self.completion, self.parent)
        # Build a stale snapshot of the same row mirroring what worker B
        # would have read before A's commit.
        stale = ChoreCompletion.objects.get(pk=self.completion.pk)
        stale.status = ChoreCompletion.Status.PENDING
        # Worker B calls approve again with the stale object — should
        # detect the real status under the lock and no-op.
        ChoreService.approve_completion(stale, self.parent)
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 1)
        self.assertEqual(
            CoinLedger.objects.filter(
                user=self.child, reason=CoinLedger.Reason.CHORE_REWARD,
            ).count(),
            1,
        )

    def test_reject_with_stale_in_memory_status_is_noop(self):
        """Same race shape, but the loser is a reject racing an approve."""
        ChoreService.approve_completion(self.completion, self.parent)
        stale = ChoreCompletion.objects.get(pk=self.completion.pk)
        stale.status = ChoreCompletion.Status.PENDING
        ChoreService.reject_completion(stale, self.parent)
        # Status stays APPROVED — the reject was racing and lost.
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, ChoreCompletion.Status.APPROVED)

    def test_zero_reward_skips_chore_ledger_entries(self):
        """Zero-reward chore doesn't post CHORE_REWARD entries. Game-loop side
        effects (e.g. daily check-in coin bonus via RPG) are out of scope
        for this assertion."""
        free = Chore.objects.create(
            title="High-five", reward_amount=Decimal("0"), coin_reward=0,
            created_by=self.parent,
        )
        completion = ChoreService.submit_completion(self.child, free)
        ChoreService.approve_completion(completion, self.parent)
        self.assertFalse(PaymentLedger.objects.filter(
            user=self.child, entry_type="chore_reward",
        ).exists())
        self.assertFalse(CoinLedger.objects.filter(
            user=self.child, reason=CoinLedger.Reason.CHORE_REWARD,
        ).exists())


class AvailableChoresTests(_Fixture):
    def test_child_sees_unassigned_and_own_assigned(self):
        unassigned = Chore.objects.create(title="A", created_by=self.parent)
        own = Chore.objects.create(title="B", created_by=self.parent, assigned_to=self.child)
        other = Chore.objects.create(title="C", created_by=self.parent, assigned_to=self.child2)

        chores = ChoreService.get_available_chores(self.child)
        ids = {c.pk for c in chores}
        self.assertIn(unassigned.pk, ids)
        self.assertIn(own.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_done_today_annotation(self):
        chore = Chore.objects.create(title="Dishes", created_by=self.parent)
        ChoreService.submit_completion(self.child, chore)
        chores = ChoreService.get_available_chores(self.child)
        first = next(c for c in chores if c.pk == chore.pk)
        self.assertTrue(first.is_done_today)
        self.assertEqual(first.today_completion_status, "pending")
