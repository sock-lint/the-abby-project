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
