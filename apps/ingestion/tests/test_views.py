"""Tests for ProjectIngestViewSet — create, retrieve, commit, destroy."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.ingestion.models import ProjectIngestionJob
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


class IngestCreateTests(_Fixture):
    def test_parent_creates_url_job(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/projects/ingest/", {
            "source_type": "url",
            "source_url": "https://example.com/project",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201, 202))
        self.assertTrue(ProjectIngestionJob.objects.exists())

    def test_child_cannot_create_job(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/projects/ingest/", {
            "source_type": "url",
            "source_url": "https://example.com/project",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_url_type_requires_source_url(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/projects/ingest/", {
            "source_type": "url",
        }, format="json")
        self.assertEqual(resp.status_code, 400)


class IngestRetrieveTests(_Fixture):
    def test_poll_job_status(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type="url",
            source_url="https://example.com", status="pending",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/projects/ingest/{job.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "pending")


class IngestCommitTests(_Fixture):
    def test_commit_ready_job_creates_project(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type="url",
            source_url="https://example.com", status="ready",
            result_json={
                "title": "Ingested Project",
                "description": "From the web",
                "milestones": [],
                "materials": [],
                "steps": [{"title": "Step 1", "description": "Do it"}],
                "resources": [],
            },
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/projects/ingest/{job.pk}/commit/", {
            "assigned_to_id": self.child.id,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        job.refresh_from_db()
        self.assertEqual(job.status, "committed")
        self.assertIsNotNone(job.project)

    def test_commit_non_ready_job_fails(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type="url",
            source_url="https://example.com", status="pending",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/projects/ingest/{job.pk}/commit/", format="json")
        self.assertEqual(resp.status_code, 400)


class IngestDiscardTests(_Fixture):
    def test_discard_job(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type="url",
            source_url="https://example.com", status="ready",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/projects/ingest/{job.pk}/")
        self.assertIn(resp.status_code, (200, 204))
        job.refresh_from_db()
        self.assertEqual(job.status, "discarded")
