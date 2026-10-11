"""Calendar exports must preserve family and individual assignment boundaries."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.chores.models import Chore
from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.google_integration.services import GoogleCalendarService
from apps.projects.models import Project, ProjectCollaborator
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family


class CalendarScopingTests(TestCase):
    def setUp(self):
        own = make_family(
            "Calendar family",
            parents=[{"username": "calendar-parent"}],
            children=[
                {"username": "calendar-child"},
                {"username": "calendar-sibling"},
                {"username": "calendar-inactive", "is_active": False},
            ],
        )
        other = make_family(
            "Other calendar family",
            parents=[{"username": "other-calendar-parent"}],
            children=[{"username": "other-calendar-child"}],
        )
        self.family = own.family
        self.parent = own.parents[0]
        self.child, self.sibling, self.inactive = own.children
        self.other_family = other.family
        self.other_parent = other.parents[0]
        self.other_child = other.children[0]

        # Fixture creation must not enqueue automatic exports. Each test
        # explicitly invokes the service against a mocked Google client.
        for task in ("sync_chore_task", "sync_project_due_date_task", "sync_time_entry_task"):
            task_patch = patch(f"apps.google_integration.tasks.{task}.delay")
            task_patch.start()
            self.addCleanup(task_patch.stop)

        for user in (self.parent, self.child, self.sibling, self.inactive, self.other_child):
            GoogleAccount.objects.create(
                user=user,
                google_id=f"synthetic-google-{user.pk}",
                google_email=f"{user.username}@example.invalid",
                encrypted_credentials=b"synthetic-unused-credentials",
                calendar_sync_enabled=True,
            )

        self.google = MagicMock()
        self.google.events.return_value.insert.return_value.execute.side_effect = (
            {"id": f"synthetic-event-{i}"} for i in range(100)
        )
        client_patch = patch.object(
            GoogleCalendarService, "get_calendar_client", return_value=self.google,
        )
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def chore(self, title, **kwargs):
        return Chore.objects.create(
            **{
                "title": title,
                "family": self.family,
                "created_by": self.parent,
                "reward_amount": "2.50",
                **kwargs,
            },
        )

    def project(self, title, **kwargs):
        return Project.objects.create(
            **{
                "title": title,
                "created_by": self.parent,
                "assigned_to": self.child,
                "due_date": timezone.localdate() + timedelta(days=3),
                **kwargs,
            },
        )

    def entry(self, project, **kwargs):
        now = timezone.now()
        return TimeEntry.objects.create(
            **{
                "user": self.child,
                "project": project,
                "status": TimeEntry.Status.COMPLETED,
                "clock_in": now - timedelta(hours=1),
                "clock_out": now,
                **kwargs,
            },
        )

    def mappings(self):
        return set(CalendarEventMapping.objects.values_list("user_id", "content_type", "object_id"))

    def test_full_sync_exports_only_approved_own_or_shared_family_duties(self):
        assigned = self.chore("My weekly duty", assigned_to=self.child, recurrence="weekly")
        shared = self.chore("Our daily duty")
        self.chore("Sibling's duty", assigned_to=self.sibling)
        self.chore("Other household's shared duty", family=self.other_family, created_by=self.other_parent)
        self.chore("Other household's assigned duty", family=self.other_family, assigned_to=self.other_child)
        self.chore("Malformed foreign duty", family=self.other_family, assigned_to=self.child)
        self.chore("Inactive duty", is_active=False)
        self.chore("Unapproved proposal", pending_parent_review=True)

        GoogleCalendarService.full_sync(self.child)

        self.assertEqual(self.mappings(), {
            (self.child.pk, "chore", assigned.pk),
            (self.child.pk, "chore", shared.pk),
        })
        bodies = [call.kwargs["body"] for call in self.google.events.return_value.insert.call_args_list]
        self.assertEqual({body["summary"] for body in bodies}, {
            "[Abby] My weekly duty", "[Abby] Our daily duty",
        })
        self.assertEqual({tuple(body["recurrence"]) for body in bodies}, {
            ("RRULE:FREQ=WEEKLY",), ("RRULE:FREQ=DAILY",),
        })

    def test_parent_full_sync_does_not_export_child_duties(self):
        self.chore("Family duty")
        self.chore("Child's duty", assigned_to=self.child)

        GoogleCalendarService.full_sync(self.parent)

        self.google.events.assert_not_called()
        self.assertEqual(self.mappings(), set())

    def test_shared_duty_fanout_uses_chore_family_even_if_creator_changed_family(self):
        chore = self.chore("Shared duty", created_by=self.other_parent)

        GoogleCalendarService.sync_chore(chore)

        self.assertEqual(self.mappings(), {
            (self.child.pk, "chore", chore.pk),
            (self.sibling.pk, "chore", chore.pk),
        })

    def test_assigned_duty_fanout_rejects_foreign_parent_and_inactive_assignees(self):
        for user in (self.other_child, self.parent, self.inactive):
            with self.subTest(user=user.username):
                GoogleCalendarService.sync_chore(self.chore("Invalid assignment", assigned_to=user))

        self.google.events.assert_not_called()
        self.assertEqual(self.mappings(), set())

    def test_inactive_or_unapproved_duties_are_not_exported_automatically(self):
        GoogleCalendarService.sync_chore(self.chore("Inactive", is_active=False))
        GoogleCalendarService.sync_chore(self.chore("Pending", pending_parent_review=True))

        self.google.events.assert_not_called()

    def test_full_sync_keeps_project_deadlines_and_completed_time_entries_personal(self):
        project = self.project("My project")
        entry = self.entry(project)
        sibling_project = self.project("Sibling project", assigned_to=self.sibling)
        self.entry(sibling_project, user=self.sibling)
        foreign_project = self.project("Foreign project", assigned_to=self.other_child, created_by=self.other_parent)
        self.entry(foreign_project, user=self.other_child)
        self.project("Unassigned family draft", assigned_to=None)
        self.entry(project, status=TimeEntry.Status.VOIDED)
        self.entry(project, clock_out=None, status=TimeEntry.Status.ACTIVE)
        self.entry(project, clock_in=timezone.now() - timedelta(days=31))

        GoogleCalendarService.full_sync(self.child)

        self.assertEqual(self.mappings(), {
            (self.child.pk, "project_due", project.pk),
            (self.child.pk, "time_entry", entry.pk),
        })

    def test_full_sync_skips_time_entry_for_project_reassigned_to_another_family(self):
        project = self.project("Former project")
        self.entry(project)
        Project.objects.filter(pk=project.pk).update(assigned_to=self.other_child, title="Other family's new title")

        GoogleCalendarService.full_sync(self.child)

        self.google.events.assert_not_called()
        self.assertEqual(self.mappings(), set())

    def test_automatic_time_export_skips_inaccessible_reassigned_project(self):
        project = self.project("Former project")
        entry = self.entry(project)
        project.assigned_to = self.other_child
        project.save()

        GoogleCalendarService.sync_time_entry(entry)

        self.google.events.assert_not_called()

    def test_collaborators_can_resync_their_own_completed_time(self):
        project = self.project("Collaborative project", assigned_to=self.sibling)
        ProjectCollaborator.objects.create(project=project, user=self.child)
        entry = self.entry(project)

        GoogleCalendarService.full_sync(self.child)

        self.assertEqual(self.mappings(), {(self.child.pk, "time_entry", entry.pk)})
