"""Clock-in owns the project relationship; note edits must not move it."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family


class TimeEntryProjectIntegrityTests(TestCase):
    def setUp(self):
        self.alpha = make_family(
            "Alpha", parents=[{"username": "entry-parent-a"}], children=[{"username": "entry-child-a"}],
        )
        self.bravo = make_family(
            "Bravo", parents=[{"username": "entry-parent-b"}], children=[{"username": "entry-child-b"}],
        )
        self.own = Project.objects.create(
            title="Own", created_by=self.alpha.parents[0], assigned_to=self.alpha.children[0],
        )
        self.foreign = Project.objects.create(
            title="Private foreign project", created_by=self.bravo.parents[0], assigned_to=self.bravo.children[0],
        )
        self.entry = TimeEntry.objects.create(
            user=self.alpha.children[0], project=self.own, clock_in=timezone.now() - timedelta(hours=1),
            clock_out=timezone.now(), status=TimeEntry.Status.COMPLETED,
        )
        self.client = APIClient()
        self.url = f"/api/time-entries/{self.entry.pk}/"

    def test_child_and_parent_cannot_reassign_entry_to_foreign_project(self):
        for user in (self.alpha.children[0], self.alpha.parents[0]):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                response = self.client.patch(self.url, {"project": self.foreign.pk}, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertNotIn(self.foreign.title, response.content.decode())
                self.entry.refresh_from_db()
                self.assertEqual(self.entry.project_id, self.own.pk)

    def test_note_edit_with_existing_project_is_allowed(self):
        self.client.force_authenticate(self.alpha.children[0])
        response = self.client.patch(self.url, {"project": self.own.pk, "notes": "Finished"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.project_id, self.own.pk)
        self.assertEqual(self.entry.notes, "Finished")
