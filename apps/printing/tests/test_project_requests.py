"""Project parts use the ordinary print lifecycle without widening visibility."""
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.printing.models import PrintRequest
from apps.printing.serializers import PrintRequestSerializer
from apps.printing.services import PrintRequestError, PrintRequestService
from apps.projects.models import Project, ProjectCollaborator
from config.tests.factories import make_family


@override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
class ProjectPrintRequestTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Project printers", parents=[{"username": "parent"}],
            children=[{"username": "builder"}, {"username": "sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        other = make_family(
            "Other makers", parents=[{"username": "other-parent"}],
            children=[{"username": "other-child"}],
        )
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        self.project = Project.objects.create(
            title="Build a marble run", assigned_to=self.child,
            created_by=self.parent, status=Project.Status.IN_PROGRESS,
        )
        self.other_project = Project.objects.create(
            title="Private other-family project", assigned_to=self.other_child,
            created_by=self.other_parent,
        )
        # Source uploads avoid model-host traffic. Link submissions also patch
        # enrichment so neither a broker nor an external page is needed.
        enrichment = patch("apps.printing.tasks.enrich_request_metadata.delay")
        enrichment.start()
        self.addCleanup(enrichment.stop)

    def submit(self, *, user=None, project_id=..., **overrides):
        self.client.force_authenticate(user or self.child)
        payload = {
            "title": "Marble funnel", "source_url": "https://example.com/model",
            "color": "green", "reason": "Guide marbles into the track",
        }
        if project_id is not ...:
            payload["project_id"] = project_id
        payload.update(overrides)
        return self.client.post("/api/print-requests/", payload, format="json")

    def test_child_request_keeps_project_context(self):
        response = self.submit(project_id=self.project.pk)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data.get("project"), self.project.pk)
        self.assertEqual(response.data.get("project_title"), self.project.title)
        saved = PrintRequest.objects.get(pk=response.data["id"])
        self.assertEqual(saved.project_id, self.project.pk)
        self.assertEqual(saved.user, self.child)
        self.assertEqual(saved.status, PrintRequest.Status.PENDING)
        self.assertEqual(saved.coins_paid, 0)

    def test_same_family_sibling_and_foreign_or_missing_projects_are_not_found(self):
        for user, project_id in (
            (self.sibling, self.project.pk),
            (self.child, self.other_project.pk),
            (self.parent, self.other_project.pk),
            (self.child, 999999),
        ):
            with self.subTest(user=user.username, project_id=project_id):
                response = self.submit(user=user, project_id=project_id, user_id=self.child.pk)
                self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(PrintRequest.objects.exists())

    def test_collaborator_can_request_for_self_but_not_a_sibling(self):
        ProjectCollaborator.objects.create(project=self.project, user=self.sibling)
        response = self.submit(user=self.sibling, project_id=self.project.pk, user_id=self.child.pk)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["user"], self.sibling.pk)
        self.assertEqual(response.data["project"], self.project.pk)

    def test_stale_cross_family_collaborator_cannot_request_or_read_project(self):
        ProjectCollaborator.objects.create(project=self.other_project, user=self.child)
        self.assertEqual(self.submit(project_id=self.other_project.pk).status_code, 404)

    def test_parent_on_behalf_requires_target_child_membership(self):
        allowed = self.submit(user=self.parent, project_id=self.project.pk, user_id=self.child.pk)
        self.assertEqual(allowed.status_code, 201, allowed.content)
        self.assertEqual(allowed.data["project"], self.project.pk)
        refused = self.submit(user=self.parent, project_id=self.project.pk, user_id=self.sibling.pk)
        self.assertEqual(refused.status_code, 404, refused.content)

    def test_request_without_project_preserves_nullable_contract(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIn("project", response.data)
        self.assertIsNone(response.data["project"])
        self.assertIsNone(response.data["project_title"])

    def test_null_project_id_is_an_unassociated_request(self):
        response = self.submit(project_id=None)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.data["project"])

    def test_invalid_project_id_is_a_field_error(self):
        for value in ("nope", 0, -1):
            with self.subTest(value=value):
                response = self.submit(project_id=value)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("project_id", response.data)

    def test_upload_keeps_project_association(self):
        self.client.force_authenticate(self.child)
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post("/api/print-requests/", {
                "model_file": SimpleUploadedFile("synthetic.stl", b"solid example\nendsolid"),
                "title": "Funnel", "color": "blue", "reason": "Project part",
                "project_id": self.project.pk,
            }, format="multipart")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["project"], self.project.pk)
        self.assertEqual(PrintRequest.objects.get(pk=response.data["id"]).project_id, self.project.pk)

    def test_project_filter_preserves_request_owner_scoping(self):
        mine = self.submit(project_id=self.project.pk).data["id"]
        ProjectCollaborator.objects.create(project=self.project, user=self.sibling)
        theirs = self.submit(user=self.sibling, project_id=self.project.pk).data["id"]
        self.submit()
        for user, expected in ((self.child, {mine}), (self.parent, {mine, theirs})):
            self.client.force_authenticate(user)
            response = self.client.get("/api/print-requests/", {"project_id": self.project.pk})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual({row["id"] for row in response.data["results"]}, expected)
        self.client.force_authenticate(self.other_child)
        self.assertEqual(self.client.get("/api/print-requests/", {"project_id": self.project.pk}).status_code, 404)

    def test_project_filter_does_not_hide_detail_or_action(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        response = self.client.get(f"/api/print-requests/{saved_id}/", {"project_id": 999999})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["project"], self.project.pk)

    def test_association_cannot_be_changed_by_editing(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        for field in ("project_id", "project"):
            response = self.client.patch(f"/api/print-requests/{saved_id}/", {field: None}, format="json")
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PrintRequest.objects.get(pk=saved_id).project_id, self.project.pk)

    def test_reassignment_hides_project_context_in_list_detail_and_actions(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        self.project.assigned_to = self.other_child
        self.project.title = "Other family's new private title"
        self.project.save(update_fields=["assigned_to", "title"])
        # Even retained collaborator membership cannot defeat the family fence.
        ProjectCollaborator.objects.create(project=self.project, user=self.child)
        for user in (self.child, self.parent):
            self.client.force_authenticate(user)
            detail = self.client.get(f"/api/print-requests/{saved_id}/")
            self.assertIsNone(detail.data["project"])
            self.assertIsNone(detail.data["project_title"])
            listed = self.client.get("/api/print-requests/").data["results"][0]
            self.assertIsNone(listed["project"])
            self.assertIsNone(listed["project_title"])
        cancelled = self.client.post(f"/api/print-requests/{saved_id}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        self.assertIsNone(cancelled.data["project"])
        self.assertIsNone(cancelled.data["project_title"])

    def test_deleting_project_preserves_request_history(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        self.project.delete()
        saved = PrintRequest.objects.get(pk=saved_id)
        self.assertIsNone(saved.project_id)
        self.assertEqual(saved.title, "Marble funnel")

    def test_serialization_without_authenticated_context_hides_project(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        saved = PrintRequest.objects.get(pk=saved_id)
        for context in ({}, {"request": SimpleNamespace(user=None)}):
            response = PrintRequestSerializer(saved, context=context).data
            self.assertIsNone(response["project"])
            self.assertIsNone(response["project_title"])

    def test_service_also_refuses_unrelated_project(self):
        with self.assertRaises(PrintRequestError):
            PrintRequestService.create_request(
                self.child, title="Part", reason="Needed", color="green",
                source_kind=PrintRequest.SourceKind.UPLOAD, project=self.other_project,
            )

    def test_access_lost_between_lookup_and_service_recheck_is_not_found(self):
        with patch("apps.printing.services.projects_for_printing", return_value=Project.objects.none()):
            response = self.submit(project_id=self.project.pk)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(PrintRequest.objects.exists())

    def test_former_assignee_loses_context_but_family_parent_retains_it(self):
        saved_id = self.submit(project_id=self.project.pk).data["id"]
        self.project.assigned_to = self.sibling
        self.project.save(update_fields=["assigned_to"])
        detail = self.client.get(f"/api/print-requests/{saved_id}/")
        self.assertIsNone(detail.data["project"])
        self.assertIsNone(detail.data["project_title"])
        self.client.force_authenticate(self.parent)
        detail = self.client.get(f"/api/print-requests/{saved_id}/")
        self.assertEqual(detail.data["project"], self.project.pk)

    def test_list_projection_batches_current_project_authorization(self):
        self.submit(project_id=self.project.pk)
        second = Project.objects.create(
            title="Build a bridge", assigned_to=self.child, created_by=self.parent,
        )
        self.submit(project_id=second.pk)
        instances = list(PrintRequest.objects.select_related("user", "decided_by").prefetch_related("jobs"))
        with self.assertNumQueries(1):
            body = PrintRequestSerializer(
                instances, many=True, context={"request": SimpleNamespace(user=self.child)},
            ).data
        self.assertEqual({row["project"] for row in body}, {self.project.pk, second.pk})
