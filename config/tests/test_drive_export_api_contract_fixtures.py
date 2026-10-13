"""Real parent-scoped Abby file exports, with only Google's network mocked."""

import io
import json
import tempfile
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_PICKER_API_KEY="synthetic-picker-key",
    GOOGLE_PICKER_APP_ID="123456789012",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class DriveExportApiFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        family = make_family(
            "Drive Export Fixture Family", family_id=33,
            parents=[{"id": 71, "username": "fixture-drive-export-parent"}],
            children=[{"id": 72, "username": "fixture-drive-export-child"}],
        )
        self.parent = family.parents[0]
        self.client.force_authenticate(self.parent)
        self.project = Project.objects.create(
            id=501, title="Science project", created_by=self.parent,
            assigned_to=family.children[0],
        )
        image = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image, format="PNG")
        self.photo = ProjectPhoto.objects.create(
            id=301, project=self.project, user=self.parent, caption="Experiment photo",
        )
        self.photo.image.save("experiment.png", ContentFile(image.getvalue()), save=True)
        for photo_id in range(302, 322):
            ProjectPhoto.objects.create(
                id=photo_id, project=self.project, user=self.parent,
                image=self.photo.image.name, caption=f"Experiment photo {photo_id}",
            )

    def test_paginated_sources_are_real_scoped_records_without_media_urls(self):
        first = self.assert_response_fixture(
            self.client.get("/api/auth/google/drive/sources/?source_type=project_photo"),
            "google-drive-sources-page-1.json",
        )
        self.assertEqual(first["count"], 21)
        second = self.assert_response_fixture(
            self.client.get(first["next"]), "google-drive-sources-page-2.json",
        )
        self.assertIsNone(second["next"])
        self.assertEqual(len(first["results"]) + len(second["results"]), 21)
        for row in first["results"] + second["results"]:
            self.assertNotIn("url", row)
            self.assertNotIn("image", row)
        self.assert_response_fixture(
            self.client.get("/api/auth/google/drive/sources/?source_type=ingestion_pdf"),
            "google-drive-sources-empty.json",
        )

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_uploaded_photo_receipt_is_canonical_without_credentials(self, google_post, google_put):
        google_post.return_value = Mock(status_code=200, headers={
            "Location": "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic-upload",
        })
        receipt = {"id": "abby-photo-1", "name": "experiment.png", "mimeType": "image/png"}
        google_put.return_value = Mock(status_code=200)
        google_put.return_value.iter_content.return_value = iter([json.dumps(receipt).encode()])
        response = self.client.post("/api/auth/google/drive/upload/", {
            "source_type": "project_photo", "source_id": "301",
            "access_token": "synthetic-drive-export-token",
        }, format="json")
        body = self.assert_response_fixture(response, "google-drive-uploaded-file.json", status=201)
        self.assertEqual(body["url"], "https://drive.google.com/file/d/abby-photo-1/view")
        self.assertNotIn("synthetic-drive-export-token", response.content.decode())
        self.assertEqual(google_put.call_args.kwargs["headers"]["Content-Type"], "image/png")
        self.assertEqual(google_put.call_count, 1)
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.image.storage.exists(self.photo.image.name))
