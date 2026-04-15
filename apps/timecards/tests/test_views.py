"""Tests for Clock/TimeEntry/Timecard HTTP endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import Project, User
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import TimecardService


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(
            username="c", password="pw", role="child", hourly_rate=Decimal("5.00"),
        )
        self.project = Project.objects.create(
            title="B", created_by=self.parent, assigned_to=self.child,
            status="active", difficulty=1,
        )
        self.client = APIClient()


class ClockViewTests(_Fixture):
    def test_get_active_entry(self):
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/clock/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json())

    def test_get_with_no_active_returns_null(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/clock/")
        self.assertEqual(resp.status_code, 200)
        # The view returns Response(None) which serializes to empty body.
        self.assertFalse(resp.content.strip() and resp.content.strip() != b"null")

    @patch("apps.timecards.services.timezone.localtime")
    def test_clock_in_action(self, mock_local):
        mock_local.return_value = timezone.make_aware(timezone.datetime(2026, 4, 15, 12, 0))
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/clock/", {
            "action": "in", "project_id": self.project.id,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(TimeEntry.objects.filter(user=self.child, status="active").exists())

    def test_clock_in_unknown_project(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/clock/", {
            "action": "in", "project_id": 99999,
        }, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_invalid_action(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/clock/", {"action": "sideways"}, format="json")
        self.assertEqual(resp.status_code, 400)


class TimeEntryViewSetTests(_Fixture):
    def test_void_parent_only(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now() - timezone.timedelta(hours=1),
            clock_out=timezone.now(),
            duration_minutes=60, status="completed",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/time-entries/{entry.id}/void/")
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/time-entries/{entry.id}/void/")
        self.assertIn(resp.status_code, (200, 204))
        entry.refresh_from_db()
        self.assertEqual(entry.status, "voided")


class TimecardViewSetTests(_Fixture):
    def _make_timecard(self):
        return Timecard.objects.create(
            user=self.child,
            week_start=date(2026, 4, 13), week_end=date(2026, 4, 19),
            total_hours=Decimal("1"), hourly_earnings=Decimal("5"),
            bonus_earnings=Decimal("0"), total_earnings=Decimal("5"),
            status="pending",
        )

    def test_list_child_scoped(self):
        self._make_timecard()
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/timecards/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)

    def test_approve_parent_only(self):
        tc = self._make_timecard()
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/timecards/{tc.id}/approve/")
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/timecards/{tc.id}/approve/", {"notes": "ok"}, format="json")
        self.assertIn(resp.status_code, (200, 204))
        tc.refresh_from_db()
        self.assertEqual(tc.status, "approved")
        self.assertEqual(tc.decided_by, self.parent)

    def test_mark_paid(self):
        tc = self._make_timecard()
        self.client.force_authenticate(self.parent)
        # Numeric amount — PaymentService.record_payout does abs() without coercion.
        resp = self.client.post(
            f"/api/timecards/{tc.id}/mark-paid/",
            {"amount": 5}, format="json",
        )
        self.assertIn(resp.status_code, (200, 204))
        tc.refresh_from_db()
        self.assertEqual(tc.status, "paid")

    def test_dispute_available_to_child(self):
        tc = self._make_timecard()
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/timecards/{tc.id}/dispute/")
        self.assertIn(resp.status_code, (200, 204))
        tc.refresh_from_db()
        self.assertEqual(tc.status, "disputed")
