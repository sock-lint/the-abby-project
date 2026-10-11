"""Weekly generation keeps open totals and append-only hourly credits in sync."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import Project, SavingsGoal
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import TimecardService
from config.tests.factories import make_family


class GenerationIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "generation-parent"}],
            children=[{"username": "generation-child", "hourly_rate": Decimal("5.00")}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.project = Project.objects.create(
            title="Repair", created_by=self.parent, assigned_to=self.child,
        )
        self.monday = date(2026, 4, 13)

    def entry(self, minutes=60):
        start = timezone.make_aware(datetime.combine(self.monday, time(12)))
        return TimeEntry.objects.create(
            user=self.child, project=self.project, status=TimeEntry.Status.COMPLETED,
            clock_in=start, clock_out=start + timedelta(minutes=minutes),
        )

    def generate(self):
        return TimecardService.generate_weekly_timecard(self.child, self.monday)

    def hourly_total(self, card):
        return PaymentLedger.objects.filter(
            timecard=card, entry_type=PaymentLedger.EntryType.HOURLY,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def test_regeneration_adds_only_missing_credit(self):
        self.entry()
        card = self.generate()
        original = PaymentLedger.objects.get(timecard=card)
        self.entry(120)
        updated = self.generate()
        self.assertEqual(updated.pk, card.pk)
        self.assertEqual(updated.hourly_earnings, Decimal("15.00"))
        self.assertEqual(self.hourly_total(card), updated.hourly_earnings)
        original.refresh_from_db()
        self.assertEqual(original.amount, Decimal("5.00"))
        count = PaymentLedger.objects.filter(timecard=card).count()
        self.generate()
        self.assertEqual(PaymentLedger.objects.filter(timecard=card).count(), count)

    def test_voiding_all_entries_reverses_open_hourly_credit(self):
        entry = self.entry()
        card = self.generate()
        entry.status = TimeEntry.Status.VOIDED
        entry.save()
        updated = self.generate()
        self.assertEqual(updated.total_hours, Decimal("0.00"))
        self.assertEqual(updated.hourly_earnings, Decimal("0.00"))
        self.assertEqual(self.hourly_total(card), Decimal("0.00"))
        self.assertEqual(
            list(PaymentLedger.objects.filter(timecard=card).order_by("pk").values_list("amount", flat=True)),
            [Decimal("5.00"), Decimal("-5.00")],
        )
        self.generate()
        self.assertEqual(PaymentLedger.objects.filter(timecard=card).count(), 2)

    def test_replacement_project_credit_does_not_unlock_goal_above_final_balance(self):
        old_project = Project.objects.create(
            title="Old attribution", created_by=self.parent, assigned_to=self.child,
        )
        old_entry = self.entry(120)
        old_entry.project = old_project
        old_entry.save()
        card = self.generate()
        goal = SavingsGoal.objects.create(user=self.child, title="Save fifteen", target_amount=15)
        old_entry.status = TimeEntry.Status.VOIDED
        old_entry.save()
        self.entry(120)
        updated = self.generate()
        self.assertEqual(self.hourly_total(card), Decimal("10.00"))
        self.assertEqual(updated.hourly_earnings, Decimal("10.00"))
        goal.refresh_from_db()
        self.assertFalse(goal.is_completed)
        self.assertEqual(
            list(PaymentLedger.objects.filter(timecard=card).order_by("pk").values_list("amount", flat=True)),
            [Decimal("10.00"), Decimal("-10.00"), Decimal("10.00")],
        )

    def test_repairs_preexisting_partial_ledger(self):
        self.entry(120)
        card = Timecard.objects.create(
            user=self.child, week_start=self.monday, week_end=self.monday + timedelta(days=6),
            total_hours=2, hourly_earnings=10, total_earnings=10,
        )
        PaymentLedger.objects.create(
            user=self.child, timecard=card, project=self.project, entry_type="hourly", amount=5,
        )
        updated = self.generate()
        self.assertEqual(self.hourly_total(card), updated.hourly_earnings)
        self.assertEqual(self.hourly_total(card), Decimal("10.00"))

    def test_new_generation_rolls_back_all_rows_when_second_credit_fails(self):
        self.entry()
        self.entry()
        original = PaymentService.record_entry
        calls = 0

        def record(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("ledger unavailable")
            return original(*args, **kwargs)

        with patch.object(PaymentService, "record_entry", side_effect=record):
            with self.assertRaisesRegex(RuntimeError, "ledger unavailable"):
                self.generate()
        self.assertFalse(Timecard.objects.filter(user=self.child).exists())
        self.assertFalse(PaymentLedger.objects.filter(user=self.child).exists())
        card = self.generate()
        self.assertEqual(card.hourly_earnings, self.hourly_total(card))

    def test_correction_failure_rolls_back_card_totals(self):
        self.entry()
        card = self.generate()
        self.entry()
        with patch.object(PaymentService, "record_entry", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.generate()
        card.refresh_from_db()
        self.assertEqual(card.hourly_earnings, Decimal("5.00"))
        self.assertEqual(self.hourly_total(card), Decimal("5.00"))
        self.assertEqual(self.generate().hourly_earnings, Decimal("10.00"))

    def test_settled_weeks_keep_totals_status_and_ledger(self):
        for status in (Timecard.Status.APPROVED, Timecard.Status.PAID):
            with self.subTest(status=status):
                TimeEntry.objects.all().delete()
                Timecard.objects.all().delete()
                self.entry()
                card = self.generate()
                card.status = status
                card.save()
                self.entry(120)
                updated = self.generate()
                self.assertEqual(updated.status, status)
                self.assertEqual(updated.total_earnings, Decimal("5.00"))
                self.assertEqual(self.hourly_total(card), Decimal("5.00"))

    def test_payout_prevents_regeneration_even_with_legacy_disputed_status(self):
        self.entry()
        card = self.generate()
        TimecardService.mark_paid(card, self.parent, "5.00")
        card.status = Timecard.Status.DISPUTED
        card.save()
        self.entry()
        self.assertEqual(self.generate().hourly_earnings, Decimal("5.00"))
        TimecardService.approve_timecard(card, self.parent)
        self.assertEqual(card.status, Timecard.Status.DISPUTED)

    def test_zero_override_is_respected_and_money_matches_posted_rounding(self):
        self.project.hourly_rate_override = Decimal("0.00")
        self.project.save()
        self.entry()
        card = self.generate()
        self.assertEqual(card.hourly_earnings, Decimal("0.00"))
        self.project.hourly_rate_override = Decimal("5.25")
        self.project.save()
        TimeEntry.objects.all().delete()
        self.entry(1)
        card = self.generate()
        self.assertEqual(card.hourly_earnings, Decimal("0.11"))
        self.assertEqual(self.hourly_total(card), card.hourly_earnings)

    def test_paid_card_cannot_be_disputed_or_reapproved_from_stale_instance(self):
        self.entry()
        card = self.generate()
        stale = Timecard.objects.get(pk=card.pk)
        TimecardService.mark_paid(card, self.parent, "5.00")
        TimecardService.approve_timecard(stale, self.parent)
        self.assertEqual(stale.status, Timecard.Status.PAID)
        client = APIClient()
        client.force_authenticate(self.child)
        response = client.post(f"/api/timecards/{card.pk}/dispute/")
        self.assertEqual(response.status_code, 400)
        card.refresh_from_db()
        self.assertEqual(card.status, Timecard.Status.PAID)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class GenerationConcurrencyTests(TransactionTestCase):
    def test_overlapping_first_generations_create_one_card_and_credit_once(self):
        family = make_family(
            parents=[{"username": "generation-race-parent"}],
            children=[{"username": "generation-race-child", "hourly_rate": Decimal("5.00")}],
        )
        child = family.children[0]
        project = Project.objects.create(
            title="Concurrent week", created_by=family.parents[0], assigned_to=child,
        )
        monday = date(2026, 4, 13)
        start = timezone.make_aware(datetime.combine(monday, time(12)))
        TimeEntry.objects.create(
            user=child, project=project, status="completed",
            clock_in=start, clock_out=start + timedelta(hours=1),
        )
        ready = Barrier(2)

        def generate():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                ready.wait(timeout=5)
                return TimecardService.generate_weekly_timecard(child, monday).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: generate(), range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Timecard.objects.filter(user=child).count(), 1)
        credits = PaymentLedger.objects.filter(user=child, entry_type="hourly")
        self.assertEqual(list(credits.values_list("amount", flat=True)), [Decimal("5.00")])
