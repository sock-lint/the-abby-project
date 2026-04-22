"""Tests for User.date_of_birth + grade_entry_year computed properties.

Exercises age_years / current_grade / school_year_label / days_until_adult
across boundary cases. Uses unittest.mock.patch to pin 'today' — this repo
does NOT use freezegun or time-machine.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


def _make_child(dob=None, grade_entry_year=None):
    return User.objects.create(
        username=f"kid-{dob}-{grade_entry_year}",
        role=User.Role.CHILD,
        date_of_birth=dob,
        grade_entry_year=grade_entry_year,
    )


class AgeYearsTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_on_exact_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        self.assertEqual(u.age_years, 15)

    @patch("apps.accounts.models.date")
    def test_day_before_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 20)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        self.assertEqual(u.age_years, 14)

    @patch("apps.accounts.models.date")
    def test_feb_29_born_in_non_leap_year_treats_mar_1_as_birthday(self, mock_date):
        # Born Feb 29, 2012. On Feb 28, 2026 (non-leap) she's still 13;
        # becomes 14 on Mar 1, 2026.
        mock_date.today.return_value = date(2026, 2, 28)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2012, 2, 29))
        self.assertEqual(u.age_years, 13)

        mock_date.today.return_value = date(2026, 3, 1)
        self.assertEqual(u.age_years, 14)

    def test_no_dob_returns_none(self):
        u = _make_child(dob=None)
        self.assertIsNone(u.age_years)


class CurrentGradeTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_post_august_bumps_to_next_grade(self, mock_date):
        mock_date.today.return_value = date(2025, 8, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 9)

    @patch("apps.accounts.models.date")
    def test_pre_august_stays_on_previous_grade(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 9)

    @patch("apps.accounts.models.date")
    def test_second_year_shows_grade_10(self, mock_date):
        mock_date.today.return_value = date(2026, 9, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 10)

    def test_no_grade_entry_year_returns_none(self):
        u = _make_child(dob=date(2011, 9, 22))
        self.assertIsNone(u.current_grade)


class SchoolYearLabelTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_freshman(self, mock_date):
        mock_date.today.return_value = date(2025, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Freshman")

    @patch("apps.accounts.models.date")
    def test_sophomore_junior_senior(self, mock_date):
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        for today, expected in [
            (date(2026, 10, 1), "Sophomore"),
            (date(2027, 10, 1), "Junior"),
            (date(2028, 10, 1), "Senior"),
        ]:
            mock_date.today.return_value = today
            self.assertEqual(u.school_year_label, expected, today)

    @patch("apps.accounts.models.date")
    def test_post_hs_format(self, mock_date):
        # Entered 9th in Aug 2025 → Senior ends Jun 2029 → first post-HS year
        # is Aug 2029 school_year=2029, age turns 18 that autumn.
        mock_date.today.return_value = date(2029, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Age 18 · 2029-30")

    @patch("apps.accounts.models.date")
    def test_pre_hs_format(self, mock_date):
        mock_date.today.return_value = date(2024, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        # grade_entry_year=2025 → in 2024-25, grade = 9 + (2024 - 2025) = 8
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Grade 8")


class DaysUntilAdultTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_counts_down_to_18th(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        # 18th birthday = 2029-04-21 — exactly 3 years = 1096 days (includes 2028 leap day)
        self.assertEqual(u.days_until_adult, 1096)

    @patch("apps.accounts.models.date")
    def test_feb_29_born_18th_falls_back_to_mar_1(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2012, 2, 29))
        # 18th year = 2030 (not a leap year) → fallback to Mar 1, 2030
        expected = (date(2030, 3, 1) - date(2026, 4, 21)).days
        self.assertEqual(u.days_until_adult, expected)

    def test_no_dob_returns_none(self):
        u = _make_child(dob=None)
        self.assertIsNone(u.days_until_adult)
