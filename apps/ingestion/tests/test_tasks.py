"""Tests for the ``run_ingestion_job`` Celery task.

The task itself is small but it owns three load-bearing contracts that the
view-level tests don't exercise:

1. Status transitions: ``pending → running → ready`` on success,
   ``pending → running → failed`` on any exception.
2. Error capture: the exception's message + traceback are stored on the
   ``error`` field, truncated to 5000 chars so a runaway stack doesn't
   blow up the row.
3. Argument forwarding: ``source_type``, ``source_url``, and (for PDFs)
   ``source_file`` are passed through to ``run_ingestion`` exactly as the
   job recorded them.

The pipeline itself is exercised in ``test_pipeline.py``; here we mock
``run_ingestion`` to keep the surface narrow.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.pipeline.base import IngestionResult, StepDraft
from apps.ingestion.tasks import run_ingestion_job
from apps.projects.models import User


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
        """When a retry fails, the previous ready result shouldn't be wiped
        — the parent can still commit from the last good run."""
        job = self._make_job(
            status=ProjectIngestionJob.Status.READY,
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
