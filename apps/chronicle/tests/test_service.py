"""Tests for ChronicleService — all writers are idempotent."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService

User = get_user_model()


class RecordFirstTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_first_call_creates_entry(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_bounty_payout",
            title="First bounty payout",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.FIRST_EVER)
        self.assertEqual(entry.event_slug, "first_bounty_payout")
        self.assertEqual(entry.occurred_on, date.today())
        self.assertEqual(entry.chapter_year, date.today().year if date.today().month >= 8 else date.today().year - 1)

    def test_duplicate_slug_returns_none(self):
        ChronicleService.record_first(self.user, event_slug="first_project_completed", title="x")
        second = ChronicleService.record_first(self.user, event_slug="first_project_completed", title="y")
        self.assertIsNone(second)
        self.assertEqual(ChronicleEntry.objects.filter(event_slug="first_project_completed").count(), 1)

    def test_accepts_custom_occurred_on(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_milestone_bonus",
            title="First milestone",
            occurred_on=date(2025, 9, 14),
        )
        self.assertEqual(entry.occurred_on, date(2025, 9, 14))
        self.assertEqual(entry.chapter_year, 2025)

    def test_related_tuple_is_written(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_legendary_badge",
            title="First legendary badge",
            related=("badge", 42),
        )
        self.assertEqual(entry.related_object_type, "badge")
        self.assertEqual(entry.related_object_id, 42)

    def test_metadata_and_icon_slug(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_exchange_approved",
            title="First exchange",
            icon_slug="coin-stack",
            metadata={"amount": 500},
        )
        self.assertEqual(entry.icon_slug, "coin-stack")
        self.assertEqual(entry.metadata, {"amount": 500})


class RecordBirthdayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21))

    def test_creates_entry_keyed_on_occurred_on(self):
        entry = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertEqual(entry.kind, ChronicleEntry.Kind.BIRTHDAY)
        self.assertEqual(entry.occurred_on, date(2026, 4, 21))
        self.assertEqual(entry.chapter_year, 2025)

    def test_second_call_same_day_returns_existing(self):
        first = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        second = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)

    def test_title_includes_age_when_known(self):
        entry = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertIn("15", entry.title)


class RecordChapterTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_chapter_start_writes_entry(self):
        entry = ChronicleService.record_chapter_start(self.user, 2025)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.CHAPTER_START)
        self.assertEqual(entry.chapter_year, 2025)
        self.assertEqual(entry.occurred_on, date(2025, 8, 1))

    def test_chapter_start_is_idempotent(self):
        ChronicleService.record_chapter_start(self.user, 2025)
        ChronicleService.record_chapter_start(self.user, 2025)
        self.assertEqual(ChronicleEntry.objects.filter(kind="chapter_start", chapter_year=2025).count(), 1)

    def test_chapter_end_writes_entry(self):
        entry = ChronicleService.record_chapter_end(self.user, 2025)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.CHAPTER_END)
        self.assertEqual(entry.chapter_year, 2025)
        self.assertEqual(entry.occurred_on, date(2026, 6, 1))

    def test_chapter_end_is_idempotent(self):
        ChronicleService.record_chapter_end(self.user, 2025)
        ChronicleService.record_chapter_end(self.user, 2025)
        self.assertEqual(ChronicleEntry.objects.filter(kind="chapter_end", chapter_year=2025).count(), 1)
