"""Zero-dollar completion keeps approval, earnings history and rewards intact."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.activity.models import ActivityEvent
from apps.payments.greenlight import balances
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import TimecardService
from config.tests.factories import make_family


class TimecardClosureIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            "Closure family", parents=[{"username": "close-parent"}],
            children=[{"username": "close-child", "hourly_rate": Decimal("5.00")}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.approved_at = timezone.make_aware(datetime(2026, 10, 12, 12))
        self.card = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_hours=Decimal("0.10"), total_earnings=Decimal("0.00"),
            status=Timecard.Status.APPROVED, decided_by=self.parent,
            decided_at=self.approved_at, parent_notes="Time reviewed",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.url = f"/api/timecards/{self.card.pk}/close/"

    def assert_no_closure(self, expected_status=Timecard.Status.APPROVED):
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, expected_status)
        self.assertFalse(ActivityEvent.objects.filter(event_type="timecard.close").exists())

    def test_closed_is_a_model_status(self):
        self.assertIn(("closed", "Closed"), Timecard.Status.choices)

    def test_zero_approved_card_closes_once_without_payout_or_rewards(self):
        money_count, coin_count = PaymentLedger.objects.count(), CoinLedger.objects.count()
        with patch("apps.achievements.services.AwardService.grant") as award:
            with patch("apps.achievements.services.BadgeService.evaluate_badges") as badges:
                for _ in range(2):
                    response = self.client.post(self.url, {}, format="json")
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(response["Content-Type"], "application/json")
                    self.assertEqual(response.json()["status"], "closed")
                award.assert_not_called()
                badges.assert_not_called()
        self.card.refresh_from_db()
        self.assertEqual(self.card.decided_by, self.parent)
        self.assertEqual(self.card.decided_at, self.approved_at)
        self.assertEqual(self.card.parent_notes, "Time reviewed")
        self.assertEqual(PaymentLedger.objects.count(), money_count)
        self.assertEqual(CoinLedger.objects.count(), coin_count)
        event = ActivityEvent.objects.get(event_type="timecard.close")
        self.assertEqual((event.actor, event.subject, event.target), (self.parent, self.child, self.card))
        self.assertEqual(event.category, "timecard")
        self.assertEqual(event.context["extras"]["total_amount"], "0.00")
        self.assertIsNone(event.money_delta)
        self.assertIsNone(event.coins_delta)
        self.assertIsNone(event.xp_delta)

    def test_close_rejects_nonzero_total_and_unapproved_status(self):
        for total, card_status in (
            ("1.00", "approved"), ("-1.00", "approved"),
            ("0.00", "pending"), ("0.00", "disputed"), ("0.00", "paid"),
        ):
            with self.subTest(total=total, status=card_status):
                Timecard.objects.filter(pk=self.card.pk).update(total_earnings=total, status=card_status)
                response = self.client.post(self.url, {}, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assert_no_closure(card_status)
        self.assertFalse(PaymentLedger.objects.filter(entry_type="payout").exists())

    def test_close_rejects_a_card_with_an_existing_payout(self):
        PaymentLedger.objects.create(
            user=self.child, timecard=self.card, amount=Decimal("-1.00"), entry_type="payout",
        )
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assert_no_closure()
        self.assertEqual(PaymentLedger.objects.filter(timecard=self.card).count(), 1)

    def test_close_is_parent_only_and_family_scoped(self):
        other = make_family("Foreign closure", parents=[{"username": "foreign-close-parent"}])
        for actor, expected_code in ((self.child, 403), (other.parents[0], 404)):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(actor)
                response = self.client.post(self.url, {}, format="json")
                self.assertEqual(response.status_code, expected_code, response.content)
                self.assert_no_closure()

    def test_service_rejects_child_and_foreign_parent(self):
        other = make_family("Foreign service closure", parents=[{"username": "foreign-service-close-parent"}])
        for actor in (self.child, other.parents[0]):
            with self.subTest(actor=actor.username):
                with self.assertRaises(PermissionDenied):
                    TimecardService.close_timecard(self.card, actor)
                self.assert_no_closure()

    def test_close_uses_fresh_total_and_status_instead_of_stale_instance(self):
        stale = Timecard.objects.get(pk=self.card.pk)
        for fields in ({"total_earnings": "1.00"}, {"total_earnings": "0.00", "status": "pending"}):
            with self.subTest(fields=fields):
                Timecard.objects.filter(pk=self.card.pk).update(**fields)
                with self.assertRaises(ValueError):
                    TimecardService.close_timecard(stale, self.parent)
                self.assert_no_closure(fields.get("status", "approved"))

    def test_close_uses_fresh_child_family_for_authorization(self):
        other = make_family("Child moved family")
        # The caller's model still has its previously loaded user/family.
        self.card.user = self.child
        User.objects.filter(pk=self.child.pk).update(family=other.family)
        with self.assertRaises(PermissionDenied):
            TimecardService.close_timecard(self.card, self.parent)
        self.assert_no_closure()

    def test_stale_close_retry_returns_the_closed_card_without_another_event(self):
        stale = Timecard.objects.get(pk=self.card.pk)
        TimecardService.close_timecard(self.card, self.parent)
        result = TimecardService.close_timecard(stale, self.parent)
        self.assertEqual((result.status, stale.status), ("closed", "closed"))
        self.assertEqual(ActivityEvent.objects.filter(event_type="timecard.close").count(), 1)

    def test_failed_activity_write_rolls_back_closure(self):
        with patch("apps.activity.services.ActivityLogService.record", side_effect=RuntimeError("close audit failure")):
            with self.assertRaisesRegex(RuntimeError, "close audit failure"):
                TimecardService.close_timecard(self.card, self.parent)
        self.assert_no_closure()

    def test_closed_week_cannot_regenerate_earnings_or_ledger(self):
        Timecard.objects.filter(pk=self.card.pk).update(status="closed")
        project = Project.objects.create(title="Later hours", created_by=self.parent, assigned_to=self.child)
        start = timezone.make_aware(datetime(2026, 10, 5, 12))
        TimeEntry.objects.create(
            user=self.child, project=project, status="completed",
            clock_in=start, clock_out=start + timedelta(hours=1),
        )
        money_count = PaymentLedger.objects.count()
        result = TimecardService.generate_weekly_timecard(self.child, self.card.week_start)
        self.assertEqual(result.status, "closed")
        self.assertEqual(result.total_hours, Decimal("0.10"))
        self.assertEqual(result.total_earnings, Decimal("0.00"))
        self.assertEqual(PaymentLedger.objects.count(), money_count)

    def test_closed_card_cannot_reapprove_rewards(self):
        Timecard.objects.filter(pk=self.card.pk).update(status="closed")
        with patch("apps.achievements.services.BadgeService.evaluate_badges") as badges:
            result = TimecardService.approve_timecard(self.card, self.parent)
            self.assertEqual(result.status, "closed")
            badges.assert_not_called()

    def test_closed_card_cannot_reopen(self):
        Timecard.objects.filter(pk=self.card.pk).update(status="closed")
        response = self.client.post(f"/api/timecards/{self.card.pk}/dispute/", {}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, "closed")
        self.assertEqual(self.card.decided_at, self.approved_at)

    def test_closed_approved_history_does_not_become_withheld_hourly(self):
        Timecard.objects.filter(pk=self.card.pk).update(status="closed")
        # Approved hourly credit offset by a separate correction leaves no
        # cash due for this card, while other approved earnings remain payable.
        for amount, kind, card in (
            ("2.00", "hourly", self.card), ("-2.00", "adjustment", self.card),
            ("5.00", "chore_reward", None),
        ):
            PaymentLedger.objects.create(user=self.child, amount=amount, entry_type=kind, timecard=card)
        self.assertEqual(balances(self.child), (Decimal("5.00"), Decimal("5.00"), Decimal("0.00")))


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class TimecardClosureConcurrencyTests(TransactionTestCase):
    def test_overlapping_close_requests_record_one_completion(self):
        family = make_family(
            "Concurrent closure", parents=[{"username": "race-close-parent"}],
            children=[{"username": "race-close-child"}],
        )
        card = Timecard.objects.create(
            user=family.children[0], week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("0.00"), status=Timecard.Status.APPROVED,
        )
        ready = Barrier(2)

        def close():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                stale = Timecard.objects.get(pk=card.pk)
                parent = User.objects.get(pk=family.parents[0].pk)
                ready.wait(timeout=5)
                return TimecardService.close_timecard(stale, parent).status
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(close) for _ in range(2)]
            self.assertEqual([future.result(timeout=15) for future in futures], ["closed"] * 2)
        self.assertEqual(ActivityEvent.objects.filter(event_type="timecard.close", target_id=card.pk).count(), 1)
        self.assertFalse(PaymentLedger.objects.filter(timecard=card).exists())
