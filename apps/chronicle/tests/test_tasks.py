"""Tests for chronicle Celery tasks — birthday gifting + chapter transitions."""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.tasks import chronicle_birthday_check
from apps.rewards.models import CoinLedger

User = get_user_model()


class BirthdayCheckTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21)
        )
        self.other = User.objects.create(
            username="not-birthday", role=User.Role.CHILD, date_of_birth=date(2010, 7, 4)
        )

    @patch("apps.chronicle.tasks.date")
    def test_creates_entry_and_grants_coins_on_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()

        entry = ChronicleEntry.objects.get(user=self.user, kind="birthday", occurred_on=date(2026, 4, 21))
        self.assertEqual(entry.metadata.get("gift_coins"), 1500)  # 100 × 15
        self.assertEqual(
            CoinLedger.objects.filter(user=self.user, reason="adjustment").count(), 1
        )

    @patch("apps.chronicle.tasks.date")
    def test_second_run_same_day_does_not_double_grant(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        chronicle_birthday_check()
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)
        self.assertEqual(
            CoinLedger.objects.filter(user=self.user, reason="adjustment").count(), 1
        )

    @patch("apps.chronicle.tasks.date")
    def test_non_birthday_user_untouched(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        self.assertFalse(ChronicleEntry.objects.filter(user=self.other).exists())

    @patch("apps.chronicle.tasks.date")
    def test_missing_dob_noop(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        User.objects.create(username="nodob", role=User.Role.CHILD)  # no DOB
        chronicle_birthday_check()  # no exceptions
        # Only our `self.user` (DOB matches today) gets an entry.
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)

    @override_settings(BIRTHDAY_COINS_PER_YEAR=50)
    @patch("apps.chronicle.tasks.date")
    def test_setting_overrides_coin_amount(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        entry = ChronicleEntry.objects.get(user=self.user, kind="birthday")
        self.assertEqual(entry.metadata.get("gift_coins"), 750)  # 50 × 15
