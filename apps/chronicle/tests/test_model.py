"""Tests for ChronicleEntry — field defaults, ordering, unique-first_ever constraint."""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


def _make_entry(user, **overrides):
    defaults = dict(
        user=user,
        kind=ChronicleEntry.Kind.MANUAL,
        occurred_on=date(2026, 4, 21),
        chapter_year=2025,
        title="Test entry",
    )
    defaults.update(overrides)
    return ChronicleEntry.objects.create(**defaults)


class ChronicleEntryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_defaults(self):
        entry = _make_entry(self.user)
        self.assertEqual(entry.summary, "")
        self.assertEqual(entry.icon_slug, "")
        self.assertEqual(entry.event_slug, "")
        self.assertEqual(entry.metadata, {})
        self.assertIsNone(entry.viewed_at)

    def test_ordering_newest_first(self):
        _make_entry(self.user, occurred_on=date(2025, 1, 1), title="old")
        _make_entry(self.user, occurred_on=date(2026, 1, 1), title="new")
        titles = list(ChronicleEntry.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["new", "old"])

    def test_unique_first_ever_per_user_and_slug(self):
        _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_bounty_payout")
        with self.assertRaises(IntegrityError):
            _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_bounty_payout")

    def test_unique_constraint_does_not_block_other_kinds(self):
        # Two MILESTONE entries with the same event_slug should be allowed at the DB level.
        # (The task-level idempotency for graduation uses get_or_create, not this constraint.)
        _make_entry(self.user, kind=ChronicleEntry.Kind.MILESTONE, event_slug="graduated_high_school")
        _make_entry(self.user, kind=ChronicleEntry.Kind.MILESTONE, event_slug="graduated_high_school")
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="graduated_high_school").count(), 2
        )

    def test_unique_first_ever_scoped_per_user(self):
        other = User.objects.create(username="sibling", role=User.Role.CHILD)
        _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_project_completed")
        # Same slug, different user: allowed.
        _make_entry(other, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_project_completed")
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="first_project_completed").count(), 2
        )
