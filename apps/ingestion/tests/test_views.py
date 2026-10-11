"""Tests for ProjectIngestViewSet — create, retrieve, update, commit, destroy."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.views import ProjectIngestViewSet
from apps.projects.models import Project, User
from config.tests.base import BaseFamilyAPITestCase


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


class IngestCommitRecoveryTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "import-parent"}]
    family_children = [{"username": "import-child"}]

    def setUp(self):
        self.client.force_authenticate(self.parents[0])
        self.job = ProjectIngestionJob.objects.create(
            created_by=self.parents[0], source_type="url", status="ready",
            result_json={
                "title": "A resumable project", "description": "Staged work",
                "steps": [{"title": "Original step"}], "materials": [], "resources": [],
            },
        )
        self.url = f"/api/projects/ingest/{self.job.pk}/commit/"
        self.payload = {"assigned_to_id": self.children[0].pk}

    def test_retried_commit_returns_existing_project_without_duplicating_steps(self):
        from apps.projects.models import Project, ProjectStep

        first = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 201)
        retry = self.client.post(self.url, {**self.payload, "title": "A retry"}, format="json")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["id"], first.json()["id"])
        self.assertEqual(retry.json()["title"], "A resumable project")
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(ProjectStep.objects.count(), 1)

    def test_deleted_project_cannot_be_recreated_by_a_stale_retry(self):
        from apps.projects.models import Project

        self.client.post(self.url, self.payload, format="json")
        self.job.refresh_from_db()
        self.job.project.delete()
        retry = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(retry.status_code, 409)
        self.assertFalse(Project.objects.exists())

    def test_worker_replay_does_not_reopen_a_committed_import(self):
        from unittest.mock import patch

        from apps.ingestion.tasks import run_ingestion_job
        from apps.projects.models import Project

        first = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 201)
        with patch("apps.ingestion.pipeline.run_ingestion") as pipeline:
            run_ingestion_job(str(self.job.pk))
            pipeline.assert_not_called()
        retry = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["id"], first.json()["id"])
        self.assertEqual(Project.objects.count(), 1)

    def test_explicit_empty_lists_preserve_removed_rows_on_creation(self):
        from apps.projects.models import MaterialItem, ProjectResource, ProjectStep

        self.job.result_json.update({
            "materials": [{"name": "A removed material"}],
            "resources": [{"url": "https://example.com/removed"}],
        })
        self.job.save(update_fields=["result_json"])
        response = self.client.post(self.url, {
            **self.payload, "materials": [], "steps": [], "resources": [],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(MaterialItem.objects.exists())
        self.assertFalse(ProjectStep.objects.exists())
        self.assertFalse(ProjectResource.objects.exists())

    def test_committed_job_cannot_be_discarded_then_recreated(self):
        self.client.post(self.url, self.payload, format="json")
        discard = self.client.delete(f"/api/projects/ingest/{self.job.pk}/")
        self.assertEqual(discard.status_code, 409)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "committed")

    def test_another_family_cannot_recover_the_committed_project(self):
        from config.tests.factories import make_family

        self.client.post(self.url, self.payload, format="json")
        other = make_family("Other import family", parents=[{"username": "other-import-parent"}])
        self.client.force_authenticate(other.parents[0])
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 404)


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


class IngestUpdateLifecycleTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "edit-import-parent"}]
    family_children = [{"username": "edit-import-child"}]

    def setUp(self):
        self.client.force_authenticate(self.parents[0])
        self.job = ProjectIngestionJob.objects.create(
            created_by=self.parents[0], source_type="url", source_url="https://example.com/original",
            status=ProjectIngestionJob.Status.READY, result_json={"title": "Original draft"},
        )
        self.url = f"/api/projects/ingest/{self.job.pk}/"

    def test_ready_patch_updates_draft_and_other_mutable_fields(self):
        response = self.client.patch(self.url, {
            "result_json": {"title": "Edited draft"}, "source_url": "https://example.com/edited",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.assertEqual(self.job.result_json, {"title": "Edited draft"})
        self.assertEqual(self.job.source_url, "https://example.com/edited")
        self.assertEqual(self.job.status, ProjectIngestionJob.Status.READY)
        self.assertIsNone(self.job.project_id)

    def test_put_uses_the_same_locked_ready_update_path(self):
        response = self.client.put(self.url, {
            "source_type": "url", "source_url": "https://example.com/replaced",
            "result_json": {"title": "Replacement draft"},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.assertEqual(self.job.result_json, {"title": "Replacement draft"})
        self.assertEqual(self.job.status, ProjectIngestionJob.Status.READY)

    def test_non_ready_patch_is_conflict_and_preserves_lifecycle_and_project(self):
        project = Project.objects.create(
            title="Committed project", created_by=self.parents[0], assigned_to=self.children[0],
        )
        for job_status in (
            ProjectIngestionJob.Status.PENDING, ProjectIngestionJob.Status.RUNNING,
            ProjectIngestionJob.Status.FAILED, ProjectIngestionJob.Status.COMMITTED,
            ProjectIngestionJob.Status.DISCARDED,
        ):
            with self.subTest(status=job_status):
                project_id = project.pk if job_status == ProjectIngestionJob.Status.COMMITTED else None
                ProjectIngestionJob.objects.filter(pk=self.job.pk).update(status=job_status, project_id=project_id)
                response = self.client.patch(self.url, {"result_json": {"title": "Late edit"}}, format="json")
                self.assertEqual(response.status_code, 409, response.content)
                self.job.refresh_from_db()
                self.assertEqual(self.job.status, job_status)
                self.assertEqual(self.job.project_id, project_id)
                self.assertEqual(self.job.result_json, {"title": "Original draft"})

    def test_stale_ready_snapshot_cannot_overwrite_concurrent_commit_or_discard(self):
        project = Project.objects.create(
            title="Committed project", created_by=self.parents[0], assigned_to=self.children[0],
        )
        for terminal in (ProjectIngestionJob.Status.COMMITTED, ProjectIngestionJob.Status.DISCARDED):
            with self.subTest(status=terminal):
                ProjectIngestionJob.objects.filter(pk=self.job.pk).update(
                    status=ProjectIngestionJob.Status.READY, project=None, result_json={"title": "Original draft"},
                )
                stale = ProjectIngestionJob.objects.get(pk=self.job.pk)
                project_id = project.pk if terminal == ProjectIngestionJob.Status.COMMITTED else None
                ProjectIngestionJob.objects.filter(pk=self.job.pk).update(
                    status=terminal, project_id=project_id, result_json={"title": "Final draft"},
                )
                with patch.object(ProjectIngestViewSet, "get_object", return_value=stale):
                    response = self.client.patch(self.url, {"result_json": {"title": "Late edit"}}, format="json")
                self.assertEqual(response.status_code, 409, response.content)
                self.job.refresh_from_db()
                self.assertEqual(self.job.status, terminal)
                self.assertEqual(self.job.project_id, project_id)
                self.assertEqual(self.job.result_json, {"title": "Final draft"})

    def test_update_remains_owner_scoped(self):
        from config.tests.factories import make_family

        other = make_family("Other editor", parents=[{"username": "other-edit-import-parent"}])
        self.client.force_authenticate(other.parents[0])
        response = self.client.patch(self.url, {"result_json": {"title": "Intrusion"}}, format="json")
        self.assertEqual(response.status_code, 404, response.content)
        self.job.refresh_from_db()
        self.assertEqual(self.job.result_json, {"title": "Original draft"})
