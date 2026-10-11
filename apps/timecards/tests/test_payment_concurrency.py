"""PostgreSQL coverage for overlapping payment requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.payments.models import PaymentLedger
from apps.timecards.models import Timecard
from apps.timecards.services import TimecardService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class TimecardPaymentConcurrencyTests(TransactionTestCase):
    def test_overlapping_requests_with_stale_instances_create_one_payout(self):
        family = make_family(
            "Concurrent payments", parents=[{"username": "concurrent-pay-parent"}],
            children=[{"username": "concurrent-pay-child"}],
        )
        card = Timecard.objects.create(
            user=family.children[0], week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("5.00"), status=Timecard.Status.APPROVED,
        )
        ready = Barrier(2)

        def pay():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                stale = Timecard.objects.get(pk=card.pk)
                parent = User.objects.get(pk=family.parents[0].pk)
                ready.wait(timeout=5)
                return TimecardService.mark_paid(stale, parent, "5.00").status
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(pay) for _ in range(2)]
            self.assertEqual([future.result(timeout=15) for future in futures], [Timecard.Status.PAID] * 2)
        payouts = PaymentLedger.objects.filter(timecard=card, entry_type=PaymentLedger.EntryType.PAYOUT)
        self.assertEqual(list(payouts.values_list("amount", flat=True)), [Decimal("-5.00")])
