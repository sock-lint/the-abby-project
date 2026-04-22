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


from apps.chronicle.tasks import chronicle_chapter_transition


class ChapterTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="kid",
            role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22),
            grade_entry_year=2025,
        )

    @patch("apps.chronicle.tasks.date")
    def test_aug_1_opens_chapter(self, mock_date):
        mock_date.today.return_value = date(2025, 8, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="chapter_start", chapter_year=2025).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_jun_1_closes_chapter_and_writes_recap(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="chapter_end", chapter_year=2025).exists()
        )
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="recap", chapter_year=2025).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_other_days_are_noop(self, mock_date):
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertFalse(ChronicleEntry.objects.filter(kind__in=["chapter_start", "chapter_end", "recap"]).exists())

    @patch("apps.chronicle.tasks.date")
    def test_senior_year_jun_1_emits_graduation(self, mock_date):
        # Entered 9th grade Aug 2025 → grade 12 is 2028-29 chapter → closes Jun 2029
        mock_date.today.return_value = date(2029, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()

        recap = ChronicleEntry.objects.get(user=self.user, kind="recap", chapter_year=2028)
        self.assertTrue(recap.metadata.get("is_graduation"))

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user, kind="milestone", event_slug="graduated_high_school"
            ).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_post_hs_year_end_is_normal_no_graduation_duplicate(self, mock_date):
        # First post-HS chapter (Aug 2029 → Jun 2030) closes without a second graduation.
        # Seed the senior-year chain first.
        mock_date.today.return_value = date(2029, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()

        mock_date.today.return_value = date(2030, 6, 1)
        chronicle_chapter_transition()

        # Exactly one graduation milestone — not two.
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="graduated_high_school").count(), 1
        )
        # And the 2029 chapter still wrapped up.
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="recap", chapter_year=2029).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_chapter_end_is_idempotent_same_day(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        chronicle_chapter_transition()
        self.assertEqual(
            ChronicleEntry.objects.filter(kind="chapter_end", chapter_year=2025).count(), 1
        )
        self.assertEqual(
            ChronicleEntry.objects.filter(kind="recap", chapter_year=2025).count(), 1
        )
