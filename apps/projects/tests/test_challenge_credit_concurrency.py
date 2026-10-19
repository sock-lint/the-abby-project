"""Initial challenge enrollment must serialize with accepted project work."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.activity.services import ActivityLogService
from apps.projects.models import Project, ProjectMilestone
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeEnrollment, ChallengeOccurrence, QuestDefinition
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class FirstCompletionCreditConcurrencyTests(TransactionTestCase):
    @staticmethod
    def _worker(action, pids=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                if pids is not None:
                    pids.append(cursor.fetchone()[0])
            return action()
        finally:
            connection.close()

    def _overlap_first_completion_and_catalog_read(self, *, milestone):
        family = make_family(
            "First completion credit",
            parents=[{"username": "first-completion-parent"}],
            children=[{"username": "first-completion-child"}],
        )
        user = family.children[0]
        trigger = "milestone_complete" if milestone else "project_complete"
        definition = QuestDefinition.objects.create(
            name="First completed work", quest_type="collection", target_value=1,
            is_system=True, trigger_filter={"allowed_triggers": [trigger]},
        )
        project = Project.objects.create(
            title="First project", created_by=family.parents[0], assigned_to=user,
            status="in_progress",
        )
        source = ProjectMilestone.objects.create(project=project, title="First milestone") if milestone else project
        source_saved, release = Event(), Event()
        original_record = ActivityLogService.record
        reader_pids = []

        def pause_after_completion_timestamp(**kwargs):
            if kwargs["event_type"] == ("milestone.complete" if milestone else "project.complete"):
                source_saved.set()
                if not release.wait(10):
                    raise TimeoutError("First completion was not released")
            return original_record(**kwargs)

        def complete():
            if milestone:
                source.is_completed = True
            else:
                source.status = "completed"
            source.save()
            return source

        with patch.object(ActivityLogService, "record", pause_after_completion_timestamp), ThreadPoolExecutor(max_workers=2) as pool:
            source_future = pool.submit(self._worker, complete)
            reader_future = None
            blocked = False
            try:
                self.assertTrue(source_saved.wait(5))
                reader_future = pool.submit(self._worker, lambda: list_goals(user), reader_pids)
                deadline = monotonic() + 5
                while monotonic() < deadline and not reader_future.done():
                    if reader_pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [reader_pids[0]])
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            blocked = True
                            break
                    sleep(0.01)
            finally:
                release.set()
            source_future.result(timeout=20)
            if reader_future:
                reader_future.result(timeout=20)

        source.refresh_from_db()
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(
            (occurrence.starts_at, occurrence.progress, occurrence.status),
            (source.completed_at, 1, "completed"),
        )
        self.assertEqual(ChallengeEnrollment.objects.get(user=user).starts_at, source.completed_at)
        self.assertTrue(blocked, "Initial catalog enrollment bypassed the accepted completion's user lock")

    def test_first_project_completion_keeps_credit_when_initial_catalog_read_overlaps(self):
        self._overlap_first_completion_and_catalog_read(milestone=False)

    def test_first_milestone_completion_keeps_credit_when_initial_catalog_read_overlaps(self):
        self._overlap_first_completion_and_catalog_read(milestone=True)

    def test_applying_plan_to_completed_project_does_not_invert_child_gate(self):
        from apps.projects.planning import append_project_plan, project_plan_snapshot

        family = make_family(
            "Completed project plan",
            parents=[{"username": "completed-plan-parent"}],
            children=[{"username": "completed-plan-child"}],
        )
        project = Project.objects.create(
            title="Completed project", created_by=family.parents[0],
            assigned_to=family.children[0], status="completed",
        )
        version, _ = project_plan_snapshot(project)
        project_locked, release = Event(), Event()
        writer_pids = []

        def pause_while_plan_owns_project(*args, **kwargs):
            project_locked.set()
            if not release.wait(10):
                raise TimeoutError("Project plan save was not released")
            return append_project_plan(*args, **kwargs)

        def apply_plan():
            client = APIClient()
            client.force_authenticate(family.parents[0])
            response = client.post(f"/api/projects/{project.pk}/apply-plan/", {
                "plan_version": version,
                "plan": {"steps": [{"title": "Extra instruction"}]},
            }, format="json")
            return response.status_code, response.content

        with patch("apps.projects.planning.append_project_plan", pause_while_plan_owns_project), ThreadPoolExecutor(max_workers=2) as pool:
            plan_future = pool.submit(self._worker, apply_plan)
            writer_future = None
            blocked = False
            try:
                self.assertTrue(project_locked.wait(5))
                # A full completed save takes the child gate before waiting on
                # the project row. The plan only saves updated_at and must not
                # attempt that gate after already locking the project.
                writer_future = pool.submit(self._worker, project.save, writer_pids)
                deadline = monotonic() + 5
                while monotonic() < deadline and not writer_future.done():
                    if writer_pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [writer_pids[0]])
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            blocked = True
                            break
                    sleep(0.01)
            finally:
                release.set()
            status_code, body = plan_future.result(timeout=20)
            if writer_future:
                writer_future.result(timeout=20)

        self.assertTrue(blocked, "Concurrent save did not overlap the locked plan update")
        self.assertEqual(status_code, 200, body)
        self.assertEqual(list(project.steps.values_list("title", flat=True)), ["Extra instruction"])
