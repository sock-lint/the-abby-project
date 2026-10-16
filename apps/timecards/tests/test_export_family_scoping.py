"""CSV endpoints preserve their format while enforcing family/self access."""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.timecards.models import Timecard, TimeEntry
from config.tests.factories import make_family


class ExportFamilyScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = make_family(
            "CSV Alpha",
            parents=[{"username": "csv-parent-a"}, {"username": "csv-coparent-a", "is_staff": True}],
            children=[
                {"username": "csv-child-a", "display_name": "Child, Alpha"},
                {"username": "csv-sibling-a"},
            ],
        )
        cls.bravo = make_family(
            "CSV Bravo", parents=[{"username": "csv-parent-b"}],
            children=[{"username": "csv-child-b"}],
        )
        cls.child = cls.alpha.children[0]
        cls.users = cls.alpha.parents + cls.alpha.children + cls.bravo.parents + cls.bravo.children
        for user in cls.users:
            Token.objects.create(user=user)
            project = Project.objects.create(
                title=f"Project, {user.username}", created_by=user, assigned_to=user,
            )
            clock_in = datetime(2026, 10, 6, 15, 5, tzinfo=timezone.utc)
            TimeEntry.objects.create(
                user=user, project=project, clock_in=clock_in,
                clock_out=clock_in + timedelta(minutes=75),
                notes='Built, tested\n"Finished"', status=TimeEntry.Status.COMPLETED,
            )
            earlier = clock_in - timedelta(days=1)
            for status, clock_out in (
                (TimeEntry.Status.ACTIVE, None),
                (TimeEntry.Status.VOIDED, earlier + timedelta(minutes=75)),
            ):
                TimeEntry.objects.create(
                    user=user, project=project, clock_in=earlier,
                    clock_out=clock_out, status=status,
                )
            Timecard.objects.create(
                user=user, week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
                total_hours=Decimal("1.25"), hourly_earnings=Decimal("10.25"),
                bonus_earnings=Decimal("2.50"), total_earnings=Decimal("12.75"),
                status=Timecard.Status.APPROVED,
            )
        for index, status in enumerate(("pending", "paid", "closed", "disputed"), start=1):
            week_start = date(2026, 10, 5) - timedelta(weeks=index)
            Timecard.objects.create(
                user=cls.child, week_start=week_start, week_end=week_start + timedelta(days=6),
                status=status,
            )

    def setUp(self):
        self.client = APIClient()

    def export_rows(self, user, endpoint, filename):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get(user=user).key}")
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="{filename}"')
        return list(csv.reader(io.StringIO(response.content.decode())))

    def assert_parent_scope(self, endpoint, filename, user_column):
        for family in (self.alpha, self.bravo):
            expected = [user.display_label for user in family.parents + family.children]
            if family is self.alpha and user_column == 2:
                expected.extend([self.child.display_label] * 4)
            for parent in family.parents:
                with self.subTest(parent=parent.username):
                    rows = self.export_rows(parent, endpoint, filename)
                    self.assertCountEqual([row[user_column] for row in rows[1:]], expected)

    def test_parent_timecards_are_family_scoped(self):
        self.assert_parent_scope("/api/export/timecards/", "timecards.csv", 2)

    def test_parent_time_entries_are_family_scoped(self):
        self.assert_parent_scope("/api/export/time-entries/", "time_entries.csv", 1)

    def assert_child_scope(self, endpoint, filename, user_column):
        for child in self.alpha.children + self.bravo.children:
            with self.subTest(child=child.username):
                rows = self.export_rows(child, endpoint, filename)
                count = 5 if child == self.child and user_column == 2 else 1
                self.assertEqual([row[user_column] for row in rows[1:]], [child.display_label] * count)

    def test_child_timecards_exclude_siblings_and_other_families(self):
        self.assert_child_scope("/api/export/timecards/", "timecards.csv", 2)

    def test_child_time_entries_exclude_siblings_and_other_families(self):
        self.assert_child_scope("/api/export/time-entries/", "time_entries.csv", 1)

    def test_timecard_csv_values_and_raw_statuses_are_compatible(self):
        rows = self.export_rows(self.child, "/api/export/timecards/", "timecards.csv")
        self.assertEqual(rows[0], [
            "Week Start", "Week End", "User", "Total Hours",
            "Hourly Earnings", "Bonus Earnings", "Total Earnings", "Status",
        ])
        self.assertEqual(rows[1], [
            "2026-10-05", "2026-10-11", "Child, Alpha", "1.25", "10.25", "2.50", "12.75", "approved",
        ])
        self.assertEqual(rows[2:], [
            ["2026-09-28", "2026-10-04", "Child, Alpha", "0.00", "0.00", "0.00", "0.00", "pending"],
            ["2026-09-21", "2026-09-27", "Child, Alpha", "0.00", "0.00", "0.00", "0.00", "paid"],
            ["2026-09-14", "2026-09-20", "Child, Alpha", "0.00", "0.00", "0.00", "0.00", "closed"],
            ["2026-09-07", "2026-09-13", "Child, Alpha", "0.00", "0.00", "0.00", "0.00", "disputed"],
        ])

    def test_time_entry_csv_values_and_completed_only_filter_are_compatible(self):
        rows = self.export_rows(self.child, "/api/export/time-entries/", "time_entries.csv")
        self.assertEqual(rows, [
            ["Date", "User", "Project", "Clock In", "Clock Out", "Duration (min)", "Notes", "Status"],
            [
                "2026-10-06", "Child, Alpha", "Project, csv-child-a", "15:05", "16:20", "75",
                'Built, tested\n"Finished"', "completed",
            ],
        ])

    def test_anonymous_timecard_export_is_rejected(self):
        response = self.client.get("/api/export/timecards/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Token")
        self.assertEqual(response.json(), {"detail": "Authentication credentials were not provided."})

    def test_anonymous_time_entry_export_is_rejected(self):
        response = self.client.get("/api/export/time-entries/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Token")
        self.assertEqual(response.json(), {"detail": "Authentication credentials were not provided."})
