"""Future birthday gifts are fixed; earlier receipts and balances stay saved."""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.tasks import chronicle_birthday_check
from apps.rewards.models import CoinLedger


TODAY = date(2026, 10, 23)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FixedBirthdayGiftTests(TestCase):
    def child(self, name, year):
        return get_user_model().objects.create_user(
            username=name, role="child", date_of_birth=date(year, 10, 23),
        )

    def celebrate(self):
        with patch("apps.chronicle.tasks.date") as clock:
            clock.today.return_value = TODAY
            clock.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            return chronicle_birthday_check()

    def test_future_gifts_are_two_hundred_for_different_ages(self):
        young, older = self.child("young", 2018), self.child("older", 2011)
        self.celebrate()
        for child in (young, older):
            with self.subTest(child=child.pk):
                self.assertEqual(CoinLedger.objects.get(user=child).amount, 200)
                self.assertEqual(ChronicleEntry.objects.get(user=child, kind="birthday").metadata["gift_coins"], 200)

    def test_existing_birthday_receipt_and_balance_are_never_repriced(self):
        child = self.child("established", 2011)
        entry = ChronicleEntry.objects.create(
            user=child, kind="birthday", occurred_on=TODAY, chapter_year=2026,
            title="Saved birthday", metadata={"gift_coins": 1500},
        )
        ledger = CoinLedger.objects.create(user=child, amount=1500, reason="adjustment", description="birthday_gift")
        self.celebrate()
        entry.refresh_from_db()
        ledger.refresh_from_db()
        self.assertEqual(entry.metadata, {"gift_coins": 1500})
        self.assertEqual(ledger.amount, 1500)
        self.assertEqual(CoinLedger.objects.filter(user=child).count(), 1)

    @override_settings(BIRTHDAY_COIN_GIFT=125)
    def test_fixed_gift_setting_and_same_day_retry_preserve_the_first_receipt(self):
        child = self.child("configured", 2011)
        self.celebrate()
        with override_settings(BIRTHDAY_COIN_GIFT=900):
            self.celebrate()
        self.assertEqual(CoinLedger.objects.get(user=child).amount, 125)
        self.assertEqual(ChronicleEntry.objects.get(user=child, kind="birthday").metadata["gift_coins"], 125)
