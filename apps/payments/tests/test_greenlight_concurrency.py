"""Real PostgreSQL user-lock coverage for overlapping external confirmations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.payments.greenlight import confirm_transfer
from apps.payments.models import GreenlightTransfer, PaymentLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class GreenlightConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("GL race", parents=[{"username": "gl-race-parent"}], children=[{"username": "gl-race-child"}])
        self.parent_id, self.child_id = family.parents[0].pk, family.children[0].pk
        PaymentLedger.objects.create(user_id=self.child_id, amount=Decimal("10.00"), entry_type=PaymentLedger.EntryType.CHORE_REWARD)

    def race(self, keys):
        ready = Barrier(2)

        def confirm(key):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                child, parent = User.objects.get(pk=self.child_id), User.objects.get(pk=self.parent_id)
                ready.wait(timeout=5)
                try:
                    _, created = confirm_transfer(child, parent, amount="10.00", transferred_on=date(2026, 10, 5), idempotency_key=key, reference=key)
                    return "created" if created else "existing"
                except ValidationError:
                    return "insufficient"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(confirm, key) for key in keys]
            return sorted(future.result(timeout=15) for future in futures)

    def test_same_confirmation_key_concurrently_returns_one_payment(self):
        self.assertEqual(self.race(["same-key", "same-key"]), ["created", "existing"])
        self.assertEqual(GreenlightTransfer.objects.count(), 1)
        self.assertEqual(PaymentLedger.objects.filter(entry_type=PaymentLedger.EntryType.PAYOUT).count(), 1)

    def test_different_confirmations_cannot_both_spend_the_same_payable_balance(self):
        self.assertEqual(self.race(["first-key", "second-key"]), ["created", "insufficient"])
        self.assertEqual(GreenlightTransfer.objects.count(), 1)
        self.assertEqual(PaymentLedger.objects.filter(entry_type=PaymentLedger.EntryType.PAYOUT).get().amount, Decimal("-10.00"))
