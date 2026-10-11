"""Project write scoping and exports with only non-project artifacts."""
import io
import zipfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import Creation
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project, ProjectCollaborator
from config.tests.factories import make_family


class PortfolioIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "portfolio-parent"}],
            children=[{"username": "portfolio-child"}, {"username": "portfolio-sibling"}],
        )
        foreign = make_family(
            parents=[{"username": "portfolio-foreign-parent"}],
            children=[{"username": "portfolio-foreign-child"}],
        )
        self.parent, self.child, self.sibling = family.parents[0], *family.children
        self.foreign_parent, self.foreign_child = foreign.parents[0], foreign.children[0]
        self.project = Project.objects.create(
            title="My project", created_by=self.parent, assigned_to=self.child,
        )
        self.foreign_project = Project.objects.create(
            title="Private project", created_by=self.foreign_parent, assigned_to=self.foreign_child,
        )
        self.client = APIClient()

    def image(self):
        return SimpleUploadedFile("artifact.jpg", b"artifact image", content_type="image/jpeg")

    def test_foreign_project_cannot_be_selected_on_create_or_update(self):
        photo = ProjectPhoto.objects.create(project=self.project, user=self.child, caption="original")
        for user in (self.parent, self.child):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                response = self.client.post("/api/photos/", {
                    "project": self.foreign_project.pk, "caption": "attack",
                    "video_url": "https://example.com/video",
                }, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Private project", str(response.data))
                response = self.client.patch(f"/api/photos/{photo.pk}/", {
                    "project": self.foreign_project.pk, "caption": "changed",
                }, format="json")
                self.assertEqual(response.status_code, 400)
                photo.refresh_from_db()
                self.assertEqual(photo.project_id, self.project.pk)
                self.assertEqual(photo.caption, "original")
        self.assertEqual(ProjectPhoto.objects.count(), 1)

    def test_collaborator_can_upload_and_read_accessible_project(self):
        ProjectCollaborator.objects.create(project=self.project, user=self.sibling)
        self.client.force_authenticate(self.sibling)
        response = self.client.post("/api/photos/", {
            "project": self.project.pk, "caption": "shared work",
            "video_url": "https://example.com/video",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"], self.sibling.pk)
        self.assertEqual(self.client.get(f"/api/photos/{response.data['id']}/").status_code, 200)
        self.assertEqual(len(self.client.get("/api/portfolio/").data["projects"]), 1)

    def proof(self, child, parent, status="approved"):
        assignment = HomeworkAssignment.objects.create(
            title="Essay", subject="writing", effort_level=3, due_date=date.today(),
            assigned_to=child, created_by=parent,
        )
        submission = HomeworkSubmission.objects.create(
            assignment=assignment, user=child, status=status, timeliness="on_time",
        )
        return HomeworkProof.objects.create(submission=submission, image=self.image(), caption="essay")

    def zip_names(self, user):
        self.client.force_authenticate(user)
        response = self.client.get("/api/export/portfolio/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertTrue(all(archive.read(name) == b"artifact image" for name in names))
            return names

    def test_homework_only_export_includes_approved_family_proof(self):
        proof = self.proof(self.child, self.parent)
        self.proof(self.child, self.parent, status="pending")
        self.proof(self.foreign_child, self.foreign_parent)
        for user in (self.child, self.parent):
            names = self.zip_names(user)
            self.assertEqual(len(names), 1)
            self.assertIn(f"{proof.pk}_essay.jpg", names[0])

    def test_creation_only_export_succeeds_without_project_photos(self):
        category = SkillCategory.objects.create(name="Art")
        skill = Skill.objects.create(name="Drawing", category=category)
        Creation.objects.create(
            user=self.child, image=self.image(), caption="drawing", occurred_on=date.today(),
            primary_skill=skill,
        )
        names = self.zip_names(self.child)
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("creations_Art/"))

    def test_nonimage_records_do_not_return_empty_zip(self):
        ProjectPhoto.objects.create(project=self.project, user=self.child, video_url="https://example.com/video")
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/export/portfolio/").status_code, 404)

    def test_missing_stored_images_return_retryable_error_instead_of_empty_zip(self):
        proof = self.proof(self.child, self.parent)
        proof.image.storage.delete(proof.image.name)
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/export/portfolio/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("try again", response.data["error"])
