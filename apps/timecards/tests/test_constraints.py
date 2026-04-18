"""Database-level constraint tests for TimeEntry.

The service layer (``ClockService.clock_in``) already refuses to open a
second active entry, but the ``one_active_entry_per_user`` partial
unique index is the real safety net — any code path that bypasses the
service (direct ORM writes, future MCP tools, fixture loads) must still
be blocked at the DB.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.projects.models import Project, User
from apps.timecards.models import TimeEntry


class TimeEntryActiveUniqueConstraintTests(TransactionTestCase):
    """Uses TransactionTestCase so IntegrityError actually surfaces;
    TestCase wraps each test in an atomic block which turns the
    constraint violation into a different failure shape."""

    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.project = Project.objects.create(
            title="Birdhouse", created_by=self.parent, assigned_to=self.child,
            status="active", difficulty=1,
        )

    def test_two_active_entries_per_user_raises(self):
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TimeEntry.objects.create(
                    user=self.child, project=self.project,
                    clock_in=timezone.now(), status="active",
                )

    def test_completed_entry_does_not_block_new_active(self):
        """Partial index is conditional on status='active' — a completed
        entry must not block a fresh clock-in."""
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), clock_out=timezone.now(),
            status="completed",
        )
        # Should NOT raise.
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        self.assertEqual(
            TimeEntry.objects.filter(user=self.child, status="active").count(),
            1,
        )

    def test_voided_entry_does_not_block_new_active(self):
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), clock_out=timezone.now(),
            status="voided",
        )
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        self.assertEqual(
            TimeEntry.objects.filter(user=self.child, status="active").count(),
            1,
        )

    def test_different_users_can_each_have_one_active(self):
        other = User.objects.create_user(username="c2", password="pw", role="child")
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        TimeEntry.objects.create(
            user=other, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        self.assertEqual(TimeEntry.objects.filter(status="active").count(), 2)
