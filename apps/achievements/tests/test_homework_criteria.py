"""Tests for the Planner + Punctual homework badge criteria.

Homework no longer pays money or coins — progression comes from
XP + organization badges. These criteria back the new Scholar track.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.achievements.criteria import (
    _homework_on_time_count,
    _homework_planned_ahead,
)
from apps.achievements.models import Badge
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.projects.models import User


class PlannerCriterionTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )

    def _logged_days_ahead(self, days_ahead):
        """Build an assignment created today with due_date N days ahead."""
        return HomeworkAssignment.objects.create(
            title=f"Plan+{days_ahead}",
            subject="math",
            due_date=timezone.localdate() + timedelta(days=days_ahead),
            assigned_to=self.child,
            created_by=self.child,
        )

    def test_returns_false_with_no_assignments(self):
        self.assertFalse(_homework_planned_ahead(self.child, {"count": 1}))

    def test_counts_assignments_with_enough_lead_time(self):
        self._logged_days_ahead(2)
        self._logged_days_ahead(3)
        self._logged_days_ahead(5)
        self.assertTrue(_homework_planned_ahead(
            self.child, {"count": 3, "days_ahead": 2},
        ))

    def test_skips_same_day_and_next_day_logs(self):
        # Neither of these count against days_ahead=2.
        self._logged_days_ahead(0)
        self._logged_days_ahead(1)
        self.assertFalse(_homework_planned_ahead(
            self.child, {"count": 1, "days_ahead": 2},
        ))

    def test_respects_count_threshold(self):
        self._logged_days_ahead(3)
        self.assertFalse(_homework_planned_ahead(
            self.child, {"count": 3, "days_ahead": 2},
        ))
        self._logged_days_ahead(4)
        self._logged_days_ahead(5)
        self.assertTrue(_homework_planned_ahead(
            self.child, {"count": 3, "days_ahead": 2},
        ))

    def test_ignores_inactive_assignments(self):
        a = self._logged_days_ahead(3)
        a.is_active = False
        a.save(update_fields=["is_active"])
        self.assertFalse(_homework_planned_ahead(
            self.child, {"count": 1, "days_ahead": 2},
        ))

    def test_late_evening_creation_uses_local_date_not_utc(self):
        """Regression: with USE_TZ=True and TIME_ZONE='America/Phoenix',
        an assignment created at 17:30 Phoenix has ``created_at.date()``
        in UTC = next-day. Pre-fix, the lead-time computation used the
        UTC date and was off by one for any creation in the late-evening
        window — failing the badge for users who legitimately planned
        ahead.
        """
        import datetime as dt
        # Phoenix is UTC-7; local 23:30 on 2026-04-30 = UTC 06:30 on 2026-05-01.
        # Date difference: due_date 2026-05-03 minus UTC date 2026-05-01 = 2 days,
        # but minus local date 2026-04-30 = 3 days (the user's intent).
        local_evening_utc = dt.datetime(
            2026, 5, 1, 6, 30, 0, tzinfo=dt.timezone.utc,
        )
        assignment = HomeworkAssignment.objects.create(
            title="Late-night-planned",
            subject="math",
            due_date=dt.date(2026, 5, 3),
            assigned_to=self.child,
            created_by=self.child,
        )
        # auto_now_add can't be set at create, so backdate explicitly.
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(
            created_at=local_evening_utc,
        )
        # Three days of lead time in local terms — should qualify.
        self.assertTrue(_homework_planned_ahead(
            self.child, {"count": 1, "days_ahead": 3},
        ))

    def test_uses_single_count_query_not_python_loop(self):
        """Audit follow-up: pre-fix the checker pulled every active
        HomeworkAssignment row into Python and looped to count.
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        # Seed 5 assignments so a Python-loop version would issue
        # ≥1 SELECT pulling all rows.
        for n in (2, 3, 4, 5, 6):
            self._logged_days_ahead(n)
        with CaptureQueriesContext(connection) as ctx:
            _homework_planned_ahead(
                self.child, {"count": 3, "days_ahead": 2},
            )
        homework_queries = [
            q for q in ctx.captured_queries
            if "homework_homeworkassignment" in q["sql"].lower()
        ]
        # Single COUNT(*) — the whole point of the ORM rewrite.
        self.assertEqual(
            len(homework_queries), 1,
            f"Expected 1 HomeworkAssignment query; got {len(homework_queries)}: "
            f"{[q['sql'] for q in homework_queries]}",
        )
        # And it IS a COUNT, not a SELECT-then-loop.
        self.assertIn("COUNT", homework_queries[0]["sql"].upper())


class PunctualCriterionTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p2", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )

    def _submission(self, status, timeliness):
        hw = HomeworkAssignment.objects.create(
            title=f"{status}-{timeliness}",
            subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child,
            created_by=self.parent,
        )
        return HomeworkSubmission.objects.create(
            assignment=hw,
            user=self.child,
            status=status,
            timeliness=timeliness,
        )

    def test_counts_approved_early_and_on_time(self):
        self._submission("approved", "early")
        self._submission("approved", "on_time")
        self.assertTrue(_homework_on_time_count(self.child, {"count": 2}))

    def test_skips_late_submissions(self):
        self._submission("approved", "late")
        self._submission("approved", "beyond_cutoff")
        self.assertFalse(_homework_on_time_count(self.child, {"count": 1}))

    def test_skips_pending_and_rejected(self):
        self._submission("pending", "on_time")
        self._submission("rejected", "on_time")
        self.assertFalse(_homework_on_time_count(self.child, {"count": 1}))


class HomeworkCriteriaRegisteredTests(TestCase):
    """Both criterion types must be discoverable via the enum."""

    def test_enum_values_present(self):
        self.assertIn(
            "homework_planned_ahead",
            [c.value for c in Badge.CriteriaType],
        )
        self.assertIn(
            "homework_on_time_count",
            [c.value for c in Badge.CriteriaType],
        )
