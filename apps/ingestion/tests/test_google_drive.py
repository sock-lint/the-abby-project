"""Drive PDFs use the existing parent-owned, review-before-commit pipeline."""
from __future__ import annotations

import json
import io
import tempfile
from unittest.mock import Mock, patch

import requests
from django.test import override_settings

from apps.google_integration.models import GoogleAccount
from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.pipeline.base import IngestionResult
from apps.ingestion.tasks import run_ingestion_job
from apps.projects.models import Project
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


def worksheet_pdf():
    """A small synthetic one-page PDF, including a real cross-reference table."""
    text = b"BT /F1 12 Tf 50 700 Td (Science worksheet) Tj 0 -20 Td (Step 1: Read the instructions) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(text)} >>\nstream\n".encode() + text + b"\nendstream",
    ]
    document = io.BytesIO(b"%PDF-1.4\n")
    document.seek(0, io.SEEK_END)
    offsets = []
    for index, content in enumerate(objects, start=1):
        offsets.append(document.tell())
        document.write(f"{index} 0 obj\n".encode() + content + b"\nendobj\n")
    xref_offset = document.tell()
    document.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        document.write(f"{offset:010d} 00000 n \n".encode())
    document.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return document.getvalue()


@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_PICKER_API_KEY="synthetic-picker-key",
    GOOGLE_PICKER_APP_ID="123456789012",
)
class DriveIngestionTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "drive-ingest-parent"}]
    family_children = [{"username": "drive-ingest-child"}]
    url = "/api/projects/ingest/google-drive/"
    selection = {"file_id": "school-pdf-1", "access_token": "synthetic-transient-token"}
    pdf_bytes = b"%PDF-1.7\n"

    def setUp(self):
        self.client.force_authenticate(self.parents[0])
        temp_media = tempfile.TemporaryDirectory()
        self.addCleanup(temp_media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=temp_media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

    def google_responses(self):
        metadata = Mock()
        metadata.status_code = 200
        metadata.iter_content.return_value = iter([json.dumps({
            "id": "school-pdf-1", "name": "Science worksheet.pdf", "mimeType": "application/pdf",
            "size": str(len(self.pdf_bytes)), "capabilities": {"canDownload": True},
        }).encode()])
        media = Mock()
        media.status_code = 200
        media.iter_content.return_value = iter([self.pdf_bytes])
        return [metadata, media]

    @patch("apps.google_integration.drive.requests.get")
    @patch("apps.ingestion.tasks.run_ingestion_job.delay")
    def test_selection_saves_copy_and_passes_only_job_id_to_celery(self, enqueue, google_get):
        google_get.side_effect = self.google_responses()
        response = self.client.post(self.url, self.selection, format="json")
        self.assertEqual(response.status_code, 201)
        job = ProjectIngestionJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.created_by, self.parents[0])
        self.assertEqual(job.source_type, "pdf")
        self.assertEqual(job.source_url, "https://drive.google.com/file/d/school-pdf-1/view")
        self.assertEqual(job.status, "pending")
        self.assertIsNone(job.project_id)
        with job.source_file.open("rb") as copied:
            self.assertEqual(copied.read(), self.pdf_bytes)
        enqueue.assert_called_once_with(str(job.pk))
        self.assertFalse(GoogleAccount.objects.exists())
        self.assertNotIn(self.selection["access_token"], response.content.decode())
        self.assertNotIn(self.selection["access_token"], str(job.__dict__))

    @patch("apps.google_integration.drive.requests.get")
    @patch("apps.ingestion.pipeline.run_ingestion")
    def test_worker_retry_reads_saved_copy_without_drive_token_or_another_download(self, pipeline, google_get):
        google_get.side_effect = self.google_responses()
        pipeline.return_value = IngestionResult(source_type="pdf", title="Science worksheet")
        response = self.client.post(self.url, self.selection, format="json")
        self.assertEqual(response.status_code, 201)
        job = ProjectIngestionJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.status, "ready")
        pipeline.assert_called_once()
        call = pipeline.call_args.kwargs
        self.assertEqual(call["source_type"], "pdf")
        with call["file_field"].open("rb") as copied:
            self.assertEqual(copied.read(), self.pdf_bytes)
        job.status = "failed"
        job.save(update_fields=["status"])
        run_ingestion_job(str(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "ready")
        self.assertEqual(pipeline.call_count, 2)
        self.assertEqual(google_get.call_count, 2)
        # Ready-job redelivery does not rerun the pipeline or contact Drive.
        run_ingestion_job(str(job.pk))
        self.assertEqual(pipeline.call_count, 2)
        self.assertEqual(google_get.call_count, 2)
        self.assertNotIn(self.selection["access_token"], str(job.__dict__))

    @override_settings(LLM_BACKEND="none")
    @patch("apps.google_integration.drive.requests.get")
    def test_real_pdf_pipeline_stages_selection_until_parent_commits(self, google_get):
        self.pdf_bytes = worksheet_pdf()
        google_get.side_effect = self.google_responses()
        response = self.client.post(self.url, self.selection, format="json")
        self.assertEqual(response.status_code, 201)
        job = ProjectIngestionJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.status, "ready", job.error)
        self.assertEqual(job.result_json["title"], "Science worksheet")
        self.assertEqual(job.result_json["steps"][0]["title"], "Read the instructions")
        self.assertFalse(Project.objects.exists())
        committed = self.client.post(f"/api/projects/ingest/{job.pk}/commit/", {
            "assigned_to_id": self.children[0].pk,
        }, format="json")
        self.assertEqual(committed.status_code, 201, committed.content)
        job.refresh_from_db()
        self.assertEqual(job.status, "committed")
        self.assertEqual(job.project.title, "Science worksheet")
        self.assertEqual(job.project.assigned_to, self.children[0])
        self.assertEqual(google_get.call_count, 2)

    @patch("apps.google_integration.drive.requests.get")
    @patch("apps.ingestion.tasks.run_ingestion_job.delay")
    def test_broker_fallback_uses_saved_pdf_for_ordinary_pipeline(self, enqueue, google_get):
        google_get.side_effect = self.google_responses()
        enqueue.side_effect = RuntimeError("synthetic broker unavailable")
        with patch("apps.ingestion.pipeline.run_ingestion") as pipeline:
            pipeline.return_value = IngestionResult(source_type="pdf", title="Science worksheet")
            response = self.client.post(self.url, self.selection, format="json")
        self.assertEqual(response.status_code, 201)
        pipeline.assert_called_once()
        job = ProjectIngestionJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.status, "ready")

    @patch("apps.google_integration.drive.requests.get")
    def test_anonymous_and_children_cannot_import_google_drive_pdf(self, google_get):
        for user, status_code in ((None, 401), (self.children[0], 403)):
            with self.subTest(user=user):
                self.client.force_authenticate(user=user)
                response = self.client.post(self.url, self.selection, format="json")
                self.assertEqual(response.status_code, status_code)
        google_get.assert_not_called()
        self.assertFalse(ProjectIngestionJob.objects.exists())

    @patch("apps.google_integration.drive.requests.get")
    @patch("apps.ingestion.tasks.run_ingestion_job.delay")
    def test_other_family_cannot_poll_or_discard_imported_job(self, enqueue, google_get):
        google_get.side_effect = self.google_responses()
        response = self.client.post(self.url, self.selection, format="json")
        job_url = f"/api/projects/ingest/{response.json()['id']}/"
        other = make_family("Other Drive family", parents=[{"username": "other-drive-parent"}])
        self.client.force_authenticate(other.parents[0])
        self.assertEqual(self.client.get(job_url).status_code, 404)
        self.assertEqual(self.client.delete(job_url).status_code, 404)

    @patch("apps.google_integration.drive.requests.get")
    def test_failed_download_creates_no_job_and_no_credentials(self, google_get):
        google_get.side_effect = requests.Timeout(self.selection["access_token"])
        response = self.client.post(self.url, self.selection, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProjectIngestionJob.objects.exists())
        self.assertFalse(GoogleAccount.objects.exists())
        self.assertNotIn(self.selection["access_token"], response.content.decode())

    @patch("apps.google_integration.drive.requests.get")
    @patch("apps.ingestion.tasks.run_ingestion_job.delay")
    def test_ordinary_upload_and_url_jobs_keep_existing_behavior(self, enqueue, google_get):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = self.client.post("/api/projects/ingest/", {
            "source_type": "pdf",
            "source_file": SimpleUploadedFile("worksheet.pdf", self.pdf_bytes, content_type="application/pdf"),
        }, format="multipart")
        url = self.client.post("/api/projects/ingest/", {
            "source_type": "url", "source_url": "https://example.invalid/project",
        }, format="json")
        self.assertEqual(upload.status_code, 201)
        self.assertEqual(url.status_code, 201)
        self.assertEqual(enqueue.call_count, 2)
        google_get.assert_not_called()
