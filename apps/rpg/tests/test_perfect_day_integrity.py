from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone as datetime_timezone
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
        # Actual Beat time: Oct 15 Phoenix / Oct 16 Tokyo. Current producer
        # services store the configured day, so the worker must use it too.
        now = datetime(2026, 10, 16, 6, 55, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            completion = ChoreService.submit_completion(self.child, self.chore)
            ChoreService.approve_completion(completion, self.parent)
            balance = CoinService.get_balance(self.child)
            evaluate_perfect_day_task()
            evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(completion.completed_date, date(2026, 10, 15))
        self.assertEqual(self.profile.last_active_date, completion.completed_date)
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), balance + 15)
        self.assertEqual(PerfectDayReceipt.objects.get(user=self.child).day, completion.completed_date)

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
