from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from itertools import chain, repeat
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.tasks import evaluate_perfect_day_task
from config.tests.factories import make_family


class PerfectDayIntegrityMixin:
    def setUp(self):
        household = make_family(
            parents=[{"username": "perfect-parent"}],
            children=[{"username": "perfect-child"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child = household.children[0]
        self.day = timezone.localdate()
        self.profile = self.child.character_profile
        self.profile.last_active_date = self.day
        self.profile.save(update_fields=["last_active_date"])
        self.chore = self.make_chore("Read")

    def make_chore(self, title, **kwargs):
        return Chore.objects.create(
            family=self.family, title=title, assigned_to=self.child,
            created_by=self.parent, **kwargs,
        )

    def complete(self, chore=None, status=ChoreCompletion.Status.APPROVED, day=None):
        return ChoreCompletion.objects.create(
            chore=chore or self.chore, user=self.child,
            completed_date=day or self.day, status=status,
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )

    def assert_reward_count(self, expected):
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, expected)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), expected)
        self.assertEqual(CoinService.get_balance(self.child), 15 * expected)
        self.assertEqual(Notification.objects.filter(user=self.child, notification_type="perfect_day").count(), expected)
        self.assertEqual(ActivityEvent.objects.filter(subject=self.child, event_type="system.perfect_day").count(), expected)


class PerfectDayIntegrityTests(PerfectDayIntegrityMixin, TestCase):
    def assert_no_perfect_day_bonus(self, balance):
        from apps.rpg.models import PerfectDayReceipt
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)
        self.assertEqual(CoinService.get_balance(self.child), balance)
        self.assertFalse(PerfectDayReceipt.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(user=self.child, notification_type="perfect_day").exists())
        self.assertFalse(ActivityEvent.objects.filter(subject=self.child, event_type="system.perfect_day").exists())

    def test_pending_completion_never_qualifies(self):
        self.complete(status=ChoreCompletion.Status.PENDING)
        evaluate_perfect_day_task()
        self.assert_reward_count(0)

    def test_rejected_or_withdrawn_completion_never_qualifies(self):
        self.complete(status=ChoreCompletion.Status.REJECTED)
        evaluate_perfect_day_task()
        self.assert_reward_count(0)
        ChoreCompletion.objects.all().delete()
        evaluate_perfect_day_task()
        self.assert_reward_count(0)

    def test_pending_can_qualify_after_parent_approval(self):
        completion = self.complete(status=ChoreCompletion.Status.PENDING)
        evaluate_perfect_day_task()
        self.assert_reward_count(0)
        completion.status = ChoreCompletion.Status.APPROVED
        completion.save(update_fields=["status"])
        evaluate_perfect_day_task()
        self.assert_reward_count(1)

    def test_repeated_delivery_has_one_receipt_and_payout(self):
        self.complete()
        evaluate_perfect_day_task()
        evaluate_perfect_day_task()
        self.assert_reward_count(1)
        from apps.rpg.models import PerfectDayReceipt
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child, day=self.day).count(), 1)

    def test_coin_failure_rolls_back_counter_and_receipt_before_retry(self):
        self.complete()
        award = CoinService.award_coins

        def fail_after_award(*args, **kwargs):
            award(*args, **kwargs)
            raise RuntimeError("coin failure")

        with patch.object(CoinService, "award_coins", side_effect=fail_after_award):
            with self.assertRaisesMessage(RuntimeError, "coin failure"):
                evaluate_perfect_day_task()
        self.assert_reward_count(0)
        evaluate_perfect_day_task()
        self.assert_reward_count(1)

    def test_notification_failure_rolls_back_whole_award(self):
        self.complete()
        with patch("apps.notifications.services.notify", side_effect=RuntimeError("notification failure")):
            with self.assertRaisesMessage(RuntimeError, "notification failure"):
                evaluate_perfect_day_task()
        self.assert_reward_count(0)
        evaluate_perfect_day_task()
        self.assert_reward_count(1)

    def test_only_same_family_eligible_scheduled_daily_chores_count(self):
        self.complete()
        self.make_chore("Inactive", is_active=False)
        self.make_chore("Parent proposal", pending_parent_review=True)
        self.make_chore("Weekly", recurrence=Chore.Recurrence.WEEKLY)
        self.make_chore("Once", recurrence=Chore.Recurrence.ONE_TIME)
        off_week = self.make_chore("Off week", week_schedule=Chore.WeekSchedule.ALTERNATING)
        from datetime import timedelta
        off_week.schedule_start_date = self.day + timedelta(days=7)
        off_week.save(update_fields=["schedule_start_date"])
        other = make_family("Other", parents=[{"username": "other-perfect-parent"}])
        Chore.objects.create(family=other.family, created_by=other.parents[0], title="Other household", assigned_to=None)
        evaluate_perfect_day_task()
        self.assert_reward_count(1)

    def test_normal_tokyo_chore_and_streak_activity_qualify_on_worker_day(self):
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        self.profile.last_active_date = None
        self.profile.save(update_fields=["last_active_date"])
        from apps.chores.services import ChoreService
        from apps.rpg.models import PerfectDayReceipt
        # Actual Beat time: Oct 15 Phoenix / Oct 16 Tokyo. Household schedule
        # identity and the existing worker/streak accounting day are distinct.
        now = datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
            balance = CoinService.get_balance(self.child)
            # A request-local timezone override must not change Beat's day.
            with timezone.override("Asia/Tokyo"):
                evaluate_perfect_day_task()
                evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(completion.completed_date, date(2026, 10, 16))
        self.assertEqual(completion.timing_snapshot["submitted_on"], "2026-10-16")
        self.assertEqual(completion.timing_snapshot["submitted_at"], now.isoformat())
        self.assertEqual(self.profile.last_active_date, date(2026, 10, 15))
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), balance + 15)
        self.assertEqual(PerfectDayReceipt.objects.get(user=self.child).day, date(2026, 10, 15))

    def test_tokyo_period_matching_next_worker_day_cannot_reward_yesterdays_submission_again(self):
        from apps.chores.services import ChoreService
        from apps.rpg.models import PerfectDayReceipt
        from apps.rpg.services import StreakService
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        submitted_at = datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=submitted_at):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
            evaluate_perfect_day_task()
        self.assertEqual(completion.completed_date, date(2026, 10, 16))
        # Activity on the next worker day does not reuse the prior day's chore.
        next_worker_tick = datetime(2026, 10, 17, 6, 55, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=next_worker_tick):
            StreakService.record_activity(self.child)
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
            evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), balance)
        self.assertEqual(list(PerfectDayReceipt.objects.filter(user=self.child).values_list("day", flat=True)), [date(2026, 10, 15)])

    def test_later_approval_does_not_move_a_submission_to_the_next_worker_day(self):
        from apps.chores.services import ChoreService
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        submitted_at = datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=submitted_at):
            completion = ChoreService.submit_completion(self.child, self.chore)
        approved_at = submitted_at + timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=approved_at):
            ChoreService.approve_completion(completion, self.parent)
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_active_date, date(2026, 10, 16))
        self.assert_no_perfect_day_bonus(balance)

    def test_created_at_crossing_worker_midnight_does_not_move_the_captured_submission(self):
        from apps.chores.services import ChoreService
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        submitted_at = datetime(2026, 10, 16, 6, 59, 59, 999999, tzinfo=datetime_timezone.utc)
        inserted_at = datetime(2026, 10, 16, 7, tzinfo=datetime_timezone.utc)
        # First now() captures submission; the insert and later calls cross
        # midnight. Approval/streak activity legitimately belong to Oct16.
        with patch("django.utils.timezone.now", side_effect=chain([submitted_at], repeat(inserted_at))):
            completion = ChoreService.submit_completion(self.child, self.chore)
        self.assertEqual(completion.created_at, inserted_at)
        self.assertEqual(completion.timing_snapshot["submitted_at"], submitted_at.isoformat())
        with patch("django.utils.timezone.now", return_value=inserted_at):
            ChoreService.approve_completion(completion, self.parent)
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
        self.assert_no_perfect_day_bonus(balance)

    def test_legacy_completion_uses_its_recorded_worker_date_without_timestamp_backfill(self):
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        worker_day = date(2026, 10, 15)
        self.profile.last_active_date = worker_day
        self.profile.save(update_fields=["last_active_date"])
        completion = self.complete(day=worker_day)
        ChoreCompletion.objects.filter(pk=completion.pk).update(
            created_at=datetime(2026, 10, 17, tzinfo=datetime_timezone.utc),
        )
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)):
            evaluate_perfect_day_task()
            evaluate_perfect_day_task()
        self.assert_reward_count(1)
        completion.refresh_from_db()
        self.assertIsNone(completion.timing_snapshot)
        self.assertEqual(completion.completed_date, worker_day)

    def test_malformed_or_different_version_evidence_cannot_fall_back_to_period_date(self):
        from apps.chores.services import ChoreService
        at = datetime(2026, 10, 15, 18, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
        valid = completion.timing_snapshot
        invalid_snapshots = [{}, [], *[
            {**valid, field: value} for field, value in [
                ("version", 2), ("version", "1"), ("version", True),
                ("submitted_at", None), ("submitted_at", "invalid"),
                ("submitted_at", "2026-10-15T11:00:00"),
                ("submitted_at", "9999-12-31T23:59:59-12:00"),
                ("timezone", None), ("timezone", "Unknown/Zone"),
                ("schedule", "weekly"), ("period_start", "2026-10-14"),
                ("period_end", "2026-10-16"), ("submitted_on", "2026-10-14"),
            ]
        ]]
        balance = CoinService.get_balance(self.child)
        for snapshot in invalid_snapshots:
            with self.subTest(snapshot=snapshot), patch("django.utils.timezone.now", return_value=at):
                ChoreCompletion.objects.filter(pk=completion.pk).update(timing_snapshot=snapshot)
                evaluate_perfect_day_task()
                self.assert_no_perfect_day_bonus(balance)

    def test_weekly_submission_cannot_become_daily_evidence_after_a_schedule_edit(self):
        from apps.chores.services import ChoreService
        self.chore.recurrence = Chore.Recurrence.WEEKLY
        self.chore.save(update_fields=["recurrence"])
        at = datetime(2026, 10, 19, 18, tzinfo=datetime_timezone.utc)  # Monday in Phoenix.
        with patch("django.utils.timezone.now", return_value=at):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
            self.chore.recurrence = Chore.Recurrence.DAILY
            self.chore.save(update_fields=["recurrence"])
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
        self.assertEqual(completion.completed_date, date(2026, 10, 19))
        self.assert_no_perfect_day_bonus(balance)

    def test_malformed_evidence_underflowing_worker_timezone_is_ignored(self):
        from apps.rpg.tasks import _completion_accounting_day
        completion = ChoreCompletion(
            completed_date=date(1, 1, 1), timing_snapshot={
                "version": 1, "schedule": "daily", "timezone": "Asia/Tokyo",
                "submitted_at": "0001-01-01T00:00:00+00:00",
                "submitted_on": "0001-01-01", "period_start": "0001-01-01",
                "period_end": "0001-01-01",
            },
        )
        self.assertIsNone(_completion_accounting_day(completion))

    def test_foreign_child_or_chore_approval_cannot_satisfy_local_daily_work(self):
        from apps.chores.services import ChoreService
        other = make_family("Foreign", parents=[{"username": "foreign-perfect-parent"}],
                            children=[{"username": "foreign-perfect-child"}])
        at = datetime(2026, 10, 15, 18, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
            ChoreCompletion.objects.filter(pk=completion.pk).update(user=other.children[0])
            foreign_chore = Chore.objects.create(
                family=other.family, created_by=other.parents[0], title="Foreign chore",
            )
            ChoreCompletion.objects.create(
                user=self.child, chore=foreign_chore, completed_date=completion.completed_date,
                status=ChoreCompletion.Status.APPROVED, timing_snapshot=completion.timing_snapshot,
                reward_amount_snapshot=0, coin_reward_snapshot=0,
            )
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
        self.assert_no_perfect_day_bonus(balance)

    def test_legacy_tokyo_award_backfill_prevents_same_worker_day_retry(self):
        from django.apps import apps
        from django.db import connection
        from importlib import import_module
        from types import SimpleNamespace
        from apps.rpg.models import PerfectDayReceipt
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        day = date(2026, 10, 15)
        self.profile.last_active_date = day
        self.profile.perfect_days_count = 1
        self.profile.save(update_fields=["last_active_date", "perfect_days_count"])
        self.complete(day=day)
        stamp = datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)
        ActivityEvent.objects.create(
            subject=self.child, category="system", event_type="system.perfect_day",
            summary="Perfect Day: +15 coins", coins_delta=15, occurred_at=stamp,
        )
        CoinLedger.objects.create(user=self.child, amount=15, reason="adjustment")
        migration = import_module("apps.rpg.migrations.0027_backfill_perfect_day_receipts")
        migration.backfill_perfect_day_receipts(apps, SimpleNamespace(connection=connection))
        self.assertEqual(PerfectDayReceipt.objects.get(user=self.child).day, day)
        with patch("django.utils.timezone.now", return_value=stamp):
            evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), 15)
        self.assertEqual(ActivityEvent.objects.filter(event_type="system.perfect_day").count(), 1)


class PerfectDayConcurrencyTests(PerfectDayIntegrityMixin, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_deliveries_have_one_payout(self):
        self.complete()
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return evaluate_perfect_day_task()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assert_reward_count(1)
        self.assertEqual(sum("1/" in result for result in results), 1)
