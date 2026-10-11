"""Tests for the ``run_ingestion_job`` Celery task.

The task itself is small but it owns four load-bearing contracts that the
view-level tests don't exercise:

1. Status transitions: ``pending → running → ready`` on success,
   ``pending → running → failed`` on any exception.
2. Error capture: the exception's message + traceback are stored on the
   ``error`` field, truncated to 5000 chars so a runaway stack doesn't
   blow up the row.
3. Argument forwarding: ``source_type``, ``source_url``, and (for PDFs)
   ``source_file`` are passed through to ``run_ingestion`` exactly as the
   job recorded them.
4. Claim/finish updates skip duplicate deliveries and preserve terminal
   state changes made while the pipeline is running.

The pipeline itself is exercised in ``test_pipeline.py``; here we mock
``run_ingestion`` to keep the surface narrow.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.pipeline.base import IngestionResult, StepDraft
from apps.ingestion.tasks import run_ingestion_job
from apps.projects.models import Project, User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )

    def _make_job(self, **overrides):
        defaults = {
            "created_by": self.parent,
            "source_type": ProjectIngestionJob.SourceType.URL,
            "source_url": "https://example.com/widget",
            "status": ProjectIngestionJob.Status.PENDING,
        }
        defaults.update(overrides)
        return ProjectIngestionJob.objects.create(**defaults)


class MissingJobTests(_Fixture):
    def test_returns_not_found_message_for_unknown_id(self):
        """A stale job_id (deleted between enqueue and worker pickup) is a
        no-op, not a hard failure — Celery should swallow the task quietly."""
        import uuid
        msg = run_ingestion_job(str(uuid.uuid4()))
        self.assertIn("not found", msg)


class SuccessPathTests(_Fixture):
    def test_marks_job_ready_and_stores_result(self):
        job = self._make_job()
        result = IngestionResult(
            title="Widget Project",
            description="From the web",
            steps=[StepDraft(title="Step 1", description="Do it")],
        )

        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.return_value = result
            ret = run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.READY)
        self.assertEqual(job.error, "")
        self.assertEqual(job.result_json["title"], "Widget Project")
        self.assertEqual(len(job.result_json["steps"]), 1)
        self.assertIn("ready", ret)

    def test_forwards_source_type_and_url_to_run_ingestion(self):
        job = self._make_job(
            source_type=ProjectIngestionJob.SourceType.INSTRUCTABLES,
            source_url="https://www.instructables.com/id/Foo/",
        )
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.return_value = IngestionResult(title="x")
            run_ingestion_job(str(job.pk))

        _, kwargs = mocked.call_args
        self.assertEqual(kwargs["source_type"], "instructables")
        self.assertEqual(
            kwargs["source_url"], "https://www.instructables.com/id/Foo/",
        )
        # No file field for URL-only jobs.
        self.assertIsNone(kwargs["file_field"])

    def test_pdf_source_forwards_file_field(self):
        """A PDF job has source_file set but no source_url. The task must
        pass the bound FieldFile through so the PDF ingestor can read it."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile(
            "guide.pdf", b"%PDF-1.4 stub", content_type="application/pdf",
        )
        job = self._make_job(
            source_type=ProjectIngestionJob.SourceType.PDF,
            source_url=None,
            source_file=upload,
        )
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.return_value = IngestionResult(title="From PDF")
            run_ingestion_job(str(job.pk))

        _, kwargs = mocked.call_args
        self.assertEqual(kwargs["source_type"], "pdf")
        # ``source_file`` is a FieldFile — checked by truthiness in the task.
        self.assertIsNotNone(kwargs["file_field"])

    def test_clears_prior_error_on_successful_rerun(self):
        """A re-run of a previously-failed job must wipe the stale error
        before flipping to running, otherwise the UI keeps showing the old
        traceback even after success."""
        job = self._make_job(
            status=ProjectIngestionJob.Status.FAILED,
            error="stale traceback from last attempt",
        )
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.return_value = IngestionResult(title="Recovered")
            run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.READY)
        self.assertEqual(job.error, "")

    def test_overwrites_stale_result_json(self):
        """A retry should replace the prior partial result, not merge it."""
        job = self._make_job(result_json={"title": "stale"})
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.return_value = IngestionResult(title="fresh")
            run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.result_json["title"], "fresh")


class FailurePathTests(_Fixture):
    def test_exception_marks_job_failed_with_error_message(self):
        job = self._make_job()
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.side_effect = ValueError("boom: bad URL")
            ret = run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.FAILED)
        self.assertIn("boom: bad URL", job.error)
        # Traceback is appended too — gives the parent enough context to
        # report the bug without us also tailing celery logs.
        self.assertIn("Traceback", job.error)
        self.assertIn("failed", ret)

    def test_error_field_truncated_to_5000_chars(self):
        """An exception with a runaway repr would overflow the TextField
        and slow down list views — the task caps it at 5000."""
        job = self._make_job()
        long_msg = "x" * 10_000
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.side_effect = RuntimeError(long_msg)
            run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.FAILED)
        self.assertLessEqual(len(job.error), 5000)
        # Still carries the start of the message so the parent sees the cause.
        self.assertTrue(job.error.startswith("x"))

    def test_failure_does_not_leave_stale_running_status(self):
        """If ``run_ingestion`` raises after we've stamped ``running``, the
        save must still land — otherwise a worker crash would leave the job
        looking like it's still in flight forever."""
        job = self._make_job()
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.side_effect = Exception("transport error")
            run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.FAILED)
        # And result_json wasn't half-populated.
        self.assertIsNone(job.result_json)

    def test_failure_does_not_overwrite_prior_result_json(self):
        """A failed retry preserves the prior draft for review/recovery."""
        job = self._make_job(
            status=ProjectIngestionJob.Status.FAILED,
            result_json={"title": "prior good run"},
        )
        with patch("apps.ingestion.pipeline.run_ingestion") as mocked:
            mocked.side_effect = Exception("retry blew up")
            run_ingestion_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.FAILED)
        self.assertEqual(job.result_json["title"], "prior good run")


class StatusTransitionOrderTests(_Fixture):
    def test_status_stamped_running_before_ingestion_call(self):
        """The job row is updated to ``running`` BEFORE the pipeline runs
        so the UI poller can show a spinner mid-flight rather than a
        misleading ``pending`` until the worker finishes."""
        job = self._make_job()
        observed = {}

        def _observer(**kwargs):
            row = ProjectIngestionJob.objects.get(pk=job.pk)
            observed["status_during_run"] = row.status
            return IngestionResult(title="done")

        with patch("apps.ingestion.pipeline.run_ingestion", side_effect=_observer):
            run_ingestion_job(str(job.pk))

        self.assertEqual(
            observed["status_during_run"],
            ProjectIngestionJob.Status.RUNNING,
        )
        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.READY)


class RedeliveryTests(_Fixture):
    def test_running_ready_and_terminal_jobs_do_not_run_pipeline(self):
        for status in (
            ProjectIngestionJob.Status.RUNNING, ProjectIngestionJob.Status.READY,
            ProjectIngestionJob.Status.DISCARDED, ProjectIngestionJob.Status.COMMITTED,
        ):
            with self.subTest(status=status):
                job = self._make_job(status=status, error="Existing error", result_json={"title": "Keep draft"})
                before = job.updated_at
                with patch("apps.ingestion.pipeline.run_ingestion") as pipeline:
                    message = run_ingestion_job(str(job.pk))
                pipeline.assert_not_called()
                job.refresh_from_db()
                self.assertEqual(job.status, status)
                self.assertEqual(job.error, "Existing error")
                self.assertEqual(job.result_json, {"title": "Keep draft"})
                self.assertEqual(job.updated_at, before)
                self.assertIn("skipped", message)

    def test_linked_project_blocks_claim_even_if_job_has_retryable_status(self):
        project = Project.objects.create(title="Existing project", created_by=self.parent)
        for status in (ProjectIngestionJob.Status.PENDING, ProjectIngestionJob.Status.FAILED):
            with self.subTest(status=status):
                job = self._make_job(status=status, project=project)
                with patch("apps.ingestion.pipeline.run_ingestion") as pipeline:
                    run_ingestion_job(str(job.pk))
                pipeline.assert_not_called()
                job.refresh_from_db()
                self.assertEqual(job.status, status)
                self.assertEqual(job.project_id, project.pk)

    def test_committed_project_deleted_before_redelivery_stays_committed(self):
        project = Project.objects.create(title="Deleted project", created_by=self.parent)
        job = self._make_job(status=ProjectIngestionJob.Status.COMMITTED, project=project)
        project.delete()
        with patch("apps.ingestion.pipeline.run_ingestion") as pipeline:
            run_ingestion_job(str(job.pk))
        pipeline.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.COMMITTED)
        self.assertIsNone(job.project_id)

    def test_delivery_during_pipeline_does_not_claim_running_job_again(self):
        job = self._make_job()
        nested_messages = []

        def run(**kwargs):
            if not nested_messages:
                # Set a sentinel first so the old unconditional implementation
                # fails the call-count assertion without recursing indefinitely.
                nested_messages.append(None)
                nested_messages[0] = run_ingestion_job(str(job.pk))
            return IngestionResult(title="One pipeline result")

        with patch("apps.ingestion.pipeline.run_ingestion", side_effect=run) as pipeline:
            run_ingestion_job(str(job.pk))
        pipeline.assert_called_once()
        self.assertIn("skipped", nested_messages[0])
        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.READY)


class StateChangeDuringPipelineTests(_Fixture):
    def test_finishing_worker_does_not_overwrite_discard_or_commit(self):
        for status in (ProjectIngestionJob.Status.DISCARDED, ProjectIngestionJob.Status.COMMITTED):
            for failure in (False, True):
                with self.subTest(status=status, failure=failure):
                    job = self._make_job(result_json={"title": "Prior draft"})
                    project = Project.objects.create(title="Committed project", created_by=self.parent)

                    def change_state(**kwargs):
                        ProjectIngestionJob.objects.filter(pk=job.pk).update(
                            status=status, project=project if status == ProjectIngestionJob.Status.COMMITTED else None,
                            error="New state", result_json={"title": "New draft"},
                        )
                        if failure:
                            raise ValueError("Worker failed after state change")
                        return IngestionResult(title="Worker result")

                    with patch("apps.ingestion.pipeline.run_ingestion", side_effect=change_state):
                        message = run_ingestion_job(str(job.pk))
                    job.refresh_from_db()
                    self.assertEqual(job.status, status)
                    self.assertEqual(job.error, "New state")
                    self.assertEqual(job.result_json, {"title": "New draft"})
                    self.assertEqual(
                        job.project_id, project.pk if status == ProjectIngestionJob.Status.COMMITTED else None,
                    )
                    self.assertIn("skipped", message)

    def test_deleted_job_is_not_recreated_on_success_or_failure(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                job = self._make_job()
                job_id = job.pk

                def delete_job(**kwargs):
                    ProjectIngestionJob.objects.filter(pk=job_id).delete()
                    if failure:
                        raise ValueError("Worker failed after deletion")
                    return IngestionResult(title="Worker result")

                with patch("apps.ingestion.pipeline.run_ingestion", side_effect=delete_job):
                    message = run_ingestion_job(str(job_id))
                self.assertFalse(ProjectIngestionJob.objects.filter(pk=job_id).exists())
                self.assertIn("skipped", message)

    def test_linked_project_during_run_blocks_finish_even_if_status_is_running(self):
        job = self._make_job(result_json={"title": "Prior draft"})
        project = Project.objects.create(title="Already materialized", created_by=self.parent)

        def link_project(**kwargs):
            ProjectIngestionJob.objects.filter(pk=job.pk).update(project=project)
            return IngestionResult(title="Worker result")

        with patch("apps.ingestion.pipeline.run_ingestion", side_effect=link_project):
            message = run_ingestion_job(str(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.RUNNING)
        self.assertEqual(job.result_json, {"title": "Prior draft"})
        self.assertEqual(job.project_id, project.pk)
        self.assertIn("skipped", message)

    def test_claim_and_finish_update_timestamps(self):
        job = self._make_job()
        claimed_at = job.updated_at + timedelta(seconds=1)
        finished_at = job.updated_at + timedelta(seconds=2)
        observed = []

        def observe(**kwargs):
            observed.append(ProjectIngestionJob.objects.get(pk=job.pk).updated_at)
            return IngestionResult(title="Done")

        with patch("apps.ingestion.tasks.timezone.now", side_effect=[claimed_at, finished_at]):
            with patch("apps.ingestion.pipeline.run_ingestion", side_effect=observe):
                run_ingestion_job(str(job.pk))
        job.refresh_from_db()
        self.assertEqual(observed, [claimed_at])
        self.assertEqual(job.updated_at, finished_at)
