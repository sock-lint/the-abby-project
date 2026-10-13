"""Real source scopes and stored bytes; only Google and storage failures are mocked."""
from __future__ import annotations

import io
import json
import tempfile
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import Creation
from apps.google_integration.drive_uploads import GoogleDriveUploadService
from apps.google_integration.models import GoogleAccount
from apps.google_integration.services import GoogleAuthService
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.tests.test_google_drive import worksheet_pdf
from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


TOKEN = "synthetic-transient-export-token"
SESSION_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic-upload"


def image_bytes(format="PNG"):
    data = io.BytesIO()
    Image.new("RGB", (3, 3), "white").save(data, format=format)
    return data.getvalue()


def init_response(status=200, location=SESSION_URL):
    response = Mock()
    response.status_code = status
    response.headers = {"Location": location}
    return response


def final_response(status=200, metadata=None):
    response = Mock()
    response.status_code = status
    response.iter_content.return_value = iter([json.dumps(metadata or {
        "id": "abby-file-1", "name": "photo.png", "mimeType": "image/png",
    }).encode()])
    return response


@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_PICKER_API_KEY="synthetic-picker-key", GOOGLE_PICKER_APP_ID="123456789012",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class DriveAbbySourceTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "export-parent"}, {"username": "export-coparent"}]
    family_children = [{"username": "export-child"}, {"username": "export-sibling"}]
    sources_url = "/api/auth/google/drive/sources/"
    upload_url = "/api/auth/google/drive/upload/"

    def setUp(self):
        self.client.force_authenticate(self.parents[0])
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.project = Project.objects.create(title="Family project", created_by=self.parents[0], assigned_to=self.children[0])
        self.photo = ProjectPhoto.objects.create(project=self.project, user=self.children[0], caption="Progress photo")
        self.photo.image.save("photo.png", ContentFile(image_bytes()), save=True)
        self.job = ProjectIngestionJob.objects.create(
            created_by=self.parents[0], source_type="pdf", result_json={"title": "School worksheet"}, status="ready",
        )
        self.job.source_file.save("worksheet.pdf", ContentFile(worksheet_pdf()), save=True)
        self.assignment = HomeworkAssignment.objects.create(
            title="Science homework", subject="science", due_date=timezone.localdate(),
            assigned_to=self.children[0], created_by=self.parents[0],
        )
        self.submission = HomeworkSubmission.objects.create(
            assignment=self.assignment, user=self.children[0], status="approved", timeliness="on_time",
        )
        self.proof = HomeworkProof.objects.create(submission=self.submission, caption="Homework photo")
        self.proof.image.save("proof.png", ContentFile(image_bytes()), save=True)
        category = SkillCategory.objects.create(name="Export art")
        self.skill = Skill.objects.create(name="Drawing", category=category)
        self.creation = Creation.objects.create(
            user=self.children[0], caption="Watercolor", primary_skill=self.skill, occurred_on=timezone.localdate(),
        )
        self.creation.image.save("art.png", ContentFile(image_bytes()), save=True)

    def upload(self, source_type="project_photo", source_id=None, **extra):
        return self.client.post(self.upload_url, {
            "source_type": source_type, "source_id": str(source_id or self.photo.pk), "access_token": TOKEN, **extra,
        }, format="json")

    def sources(self, source_type):
        return self.client.get(self.sources_url, {"source_type": source_type})

    def test_all_source_categories_list_only_metadata_without_media_or_storage_paths(self):
        for category, record, context in (
            ("ingestion_pdf", self.job, "School worksheet"), ("project_photo", self.photo, "Family project"),
            ("homework_proof", self.proof, "Science homework"),
            ("creation_photo", self.creation, self.children[0].display_label),
        ):
            with self.subTest(category=category):
                response = self.sources(category)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["count"], 1)
                item = response.json()["results"][0]
                self.assertEqual(set(item), {"source_type", "source_id", "title", "mime_type", "context"})
                self.assertEqual(item["source_type"], category)
                self.assertEqual(item["source_id"], str(record.pk))
                self.assertEqual(item["context"], context)
                self.assertNotIn("https://", response.content.decode())
                self.assertNotIn("portfolio/", response.content.decode())
                self.assertNotIn(TOKEN, response.content.decode())

    def test_parent_only_list_and_upload_fail_before_read_or_google_access(self):
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post, patch.object(FileSystemStorage, "open") as storage_open:
            for user, expected_status in ((None, 401), (self.children[0], 403)):
                with self.subTest(user=user):
                    self.client.force_authenticate(user=user)
                    self.assertEqual(self.sources("project_photo").status_code, expected_status)
                    self.assertEqual(self.upload().status_code, expected_status)
            google_post.assert_not_called()
            storage_open.assert_not_called()

    def test_invalid_categories_and_source_identifiers_are_rejected(self):
        for category in (None, "journal", "project_cover", "external_url"):
            response = self.client.get(self.sources_url, {} if category is None else {"source_type": category})
            self.assertEqual(response.status_code, 400)
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            for category, source_id in (("project_photo", "../private"), ("project_photo", "0"), ("project_photo", "9" * 30), ("ingestion_pdf", "not-a-uuid")):
                response = self.upload(category, source_id)
                self.assertEqual(response.status_code, 400)
            google_post.assert_not_called()

    def test_urls_storage_paths_and_client_file_contents_are_not_accepted(self):
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            for key in ("url", "source_url", "source_file", "storage_key", "folder_id", "user_id"):
                with self.subTest(key=key):
                    response = self.upload(**{key: "https://private.example.invalid/file"})
                    self.assertEqual(response.status_code, 400)
                    self.assertNotIn("private.example", response.content.decode())
            google_post.assert_not_called()

    def test_invalid_tokens_are_rejected_without_google_request(self):
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            for token in ("", "x" * 4097, "injected\r\nheader"):
                response = self.upload(access_token=token)
                self.assertEqual(response.status_code, 400)
            google_post.assert_not_called()

    def test_imported_pdf_stays_private_to_its_own_parent_and_discarded_imports_are_excluded(self):
        self.client.force_authenticate(self.parents[1])
        self.assertEqual(self.sources("ingestion_pdf").json()["count"], 0)
        self.assertEqual(self.upload("ingestion_pdf", self.job.pk).status_code, 404)
        self.client.force_authenticate(self.parents[0])
        self.job.status = "discarded"
        self.job.save(update_fields=["status"])
        self.assertEqual(self.sources("ingestion_pdf").json()["count"], 0)
        self.assertEqual(self.upload("ingestion_pdf", self.job.pk).status_code, 404)

    def test_committed_import_remains_an_owner_visible_saved_pdf(self):
        self.job.status = "committed"
        self.job.project = self.project
        self.job.save(update_fields=["status", "project"])
        self.assertEqual(self.sources("ingestion_pdf").json()["count"], 1)

    def test_image_less_records_and_external_video_links_are_omitted(self):
        ProjectPhoto.objects.create(project=self.project, user=self.parents[0], video_url="https://external.example.invalid/video")
        ProjectIngestionJob.objects.create(created_by=self.parents[0], source_type="pdf")
        self.assertEqual(self.sources("project_photo").json()["count"], 1)
        self.assertEqual(self.sources("ingestion_pdf").json()["count"], 1)

    def test_pending_and_rejected_homework_proofs_are_not_exportable(self):
        for status in ("pending", "rejected"):
            with self.subTest(status=status):
                self.submission.status = status
                self.submission.save(update_fields=["status"])
                self.assertEqual(self.sources("homework_proof").json()["count"], 0)
                self.assertEqual(self.upload("homework_proof", self.proof.pk).status_code, 404)

    def test_family_parent_can_choose_child_photos_proofs_and_creations(self):
        self.client.force_authenticate(self.parents[1])
        for category in ("project_photo", "homework_proof", "creation_photo"):
            self.assertEqual(self.sources(category).json()["count"], 1)

    def test_other_family_cannot_list_or_export_any_owned_source(self):
        other = make_family("Foreign exports", parents=[{"username": "foreign-export-parent"}])
        self.client.force_authenticate(other.parents[0])
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post, patch.object(FileSystemStorage, "open") as storage_open:
            for category, record in (("ingestion_pdf", self.job), ("project_photo", self.photo), ("homework_proof", self.proof), ("creation_photo", self.creation)):
                self.assertEqual(self.sources(category).json()["count"], 0)
                self.assertEqual(self.upload(category, record.pk).status_code, 404)
            google_post.assert_not_called()
            storage_open.assert_not_called()

    def test_project_assignee_family_controls_export_even_if_uploader_or_creator_is_foreign(self):
        other = make_family("Reassigned exports", parents=[{"username": "reassigned-export-parent"}], children=[{"username": "reassigned-export-child"}])
        self.project.assigned_to = other.children[0]
        self.project.save(update_fields=["assigned_to"])
        self.assertEqual(self.sources("project_photo").json()["count"], 0)
        self.assertEqual(self.upload().status_code, 404)
        self.client.force_authenticate(other.parents[0])
        self.assertEqual(self.sources("project_photo").json()["count"], 1)

    def test_unassigned_draft_photos_are_visible_only_to_creator_family(self):
        self.project.assigned_to = None
        self.project.save(update_fields=["assigned_to"])
        self.assertEqual(self.sources("project_photo").json()["count"], 1)
        other = make_family("Other unassigned exports", parents=[{"username": "other-unassigned-parent"}])
        self.client.force_authenticate(other.parents[0])
        self.assertEqual(self.sources("project_photo").json()["count"], 0)

    def test_pagination_is_bounded_and_links_stay_relative(self):
        for _ in range(20):
            ProjectPhoto.objects.create(project=self.project, user=self.children[0], image=self.photo.image.name)
        first = self.sources("project_photo").json()
        self.assertEqual(first["count"], 21)
        self.assertEqual(len(first["results"]), 20)
        self.assertTrue(first["next"].startswith(self.sources_url))
        self.assertNotIn("testserver", first["next"])
        second = self.client.get(first["next"]).json()
        self.assertEqual(len(second["results"]), 1)
        self.assertTrue(second["previous"].startswith(self.sources_url))
        self.assertIsNone(second["next"])

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_resumable_upload_sends_only_real_stored_photo_and_transient_authorization(self, google_post, google_put):
        account = GoogleAuthService.link_account(self.parents[0], "export-google-parent", "parent@example.invalid", {"token": "synthetic-calendar-token"})
        before = bytes(account.encrypted_credentials)
        source_before = self.photo.image.name
        google_post.return_value = init_response()
        google_put.return_value = final_response()
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), {
            "id": "abby-file-1", "title": "photo.png", "url": "https://drive.google.com/file/d/abby-file-1/view",
            "mime_type": "image/png", "resource_type": "image",
        })
        google_post.assert_called_once()
        self.assertEqual(google_post.call_args.args, ("https://www.googleapis.com/upload/drive/v3/files",))
        self.assertEqual(google_post.call_args.kwargs["params"]["uploadType"], "resumable")
        self.assertEqual(google_post.call_args.kwargs["json"], {"name": "photo.png", "mimeType": "image/png"})
        self.assertEqual(google_put.call_args.args, (SESSION_URL,))
        self.assertEqual(google_put.call_args.kwargs["data"], image_bytes())
        for call in (google_post.call_args, google_put.call_args):
            self.assertEqual(call.kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["timeout"], (5, 60))
        account.refresh_from_db()
        self.photo.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), before)
        self.assertEqual(self.photo.image.name, source_before)
        self.assertEqual(GoogleAccount.objects.count(), 1)
        self.assertNotIn(TOKEN, response.content.decode())
        self.assertNotIn(TOKEN, str(self.photo.__dict__))
        google_post.return_value.close.assert_called_once()
        google_put.return_value.close.assert_called_once()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_all_four_categories_send_stored_bytes_and_do_not_create_abby_resources(self, google_post, google_put):
        from apps.projects.models import ProjectResource

        for category, record, name, content, mime_type in (
            ("ingestion_pdf", self.job, "worksheet.pdf", worksheet_pdf(), "application/pdf"),
            ("project_photo", self.photo, "photo.png", image_bytes(), "image/png"),
            ("homework_proof", self.proof, "proof.png", image_bytes(), "image/png"),
            ("creation_photo", self.creation, "art.png", image_bytes(), "image/png"),
        ):
            with self.subTest(category=category):
                google_post.return_value = init_response()
                google_put.return_value = final_response(metadata={"id": "abby-file-1", "name": name, "mimeType": mime_type})
                response = self.upload(category, record.pk)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(google_put.call_args.kwargs["data"], content)
                self.assertEqual(response.json()["mime_type"], mime_type)
        self.assertFalse(ProjectResource.objects.exists())
        self.assertFalse(GoogleAccount.objects.exists())

    def test_missing_source_and_storage_failure_return_safe_errors(self):
        self.assertEqual(self.upload("ingestion_pdf", uuid4()).status_code, 404)
        with patch.object(FileSystemStorage, "open", side_effect=OSError("signed-secret-url")), patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            response = self.upload()
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("signed-secret-url", response.content.decode())
            google_post.assert_not_called()

    def test_damaged_storage_pointer_is_rejected_without_reading_arbitrary_keys(self):
        for name in ("portfolio/../private-journal.pdf", "https://evil.example/file", "receipts/another-family.png"):
            self.photo.image = name
            self.photo.save(update_fields=["image"])
            with patch.object(FileSystemStorage, "open") as source_open:
                self.assertEqual(self.upload().status_code, 404)
                source_open.assert_not_called()

    def test_file_limit_checks_declared_size_and_actual_bytes_even_if_storage_understates_size(self):
        with patch("apps.google_integration.drive_uploads.MAX_UPLOAD_BYTES", 8), patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            self.assertEqual(self.upload().status_code, 400)
            with patch.object(FileSystemStorage, "size", return_value=1):
                self.assertEqual(self.upload().status_code, 400)
            google_post.assert_not_called()

    def test_corrupt_and_disguised_pdf_or_image_are_rejected_without_google_write(self):
        for category, record, contents in (
            ("ingestion_pdf", self.job, b"not a PDF"), ("ingestion_pdf", self.job, b"%PDF-1.7 broken"),
            ("project_photo", self.photo, b"%PDF-1.7 disguised as a photo"),
        ):
            with self.subTest(category=category):
                field = record.source_file if category == "ingestion_pdf" else record.image
                field.save("corrupt.pdf" if category == "ingestion_pdf" else "corrupt.png", ContentFile(contents), save=True)
                with patch("apps.google_integration.drive_uploads.requests.post") as google_post:
                    self.assertEqual(self.upload(category, record.pk).status_code, 400)
                    google_post.assert_not_called()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_photo_mime_is_verified_from_bytes_and_filename_extension_is_corrected(self, google_post, google_put):
        for format, mime_type, extension in (
            ("JPEG", "image/jpeg", ".jpg"), ("WEBP", "image/webp", ".webp"),
            ("GIF", "image/gif", ".gif"), ("BMP", "image/bmp", ".bmp"), ("TIFF", "image/tiff", ".tiff"),
        ):
            with self.subTest(format=format):
                content = image_bytes(format)
                self.photo.image.save("misnamed.png", ContentFile(content), save=True)
                google_post.return_value = init_response()
                google_put.return_value = final_response(metadata={"id": "uploaded-photo", "name": f"photo{extension}", "mimeType": mime_type})
                response = self.upload()
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(google_put.call_args.kwargs["data"], content)
                self.assertEqual(google_put.call_args.kwargs["headers"]["Content-Type"], mime_type)
                self.assertTrue(google_post.call_args.kwargs["json"]["name"].endswith(extension))

    def test_unknown_photo_format_has_clear_error_without_google_write(self):
        self.photo.image.save("unknown.gif", ContentFile(b"unknown image data"), save=True)
        with patch("apps.google_integration.drive_uploads.requests.post") as google_post:
            response = self.upload()
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not contain a readable photo", response.content.decode())
        google_post.assert_not_called()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_animated_gif_keeps_original_frames_and_a_matching_filename(self, google_post, google_put):
        frames = [Image.new("RGB", (3, 3), color) for color in ("red", "green")]
        data = io.BytesIO()
        frames[0].save(data, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        original = data.getvalue()
        self.photo.image.save("animation.gif", ContentFile(original), save=True)
        google_post.return_value = init_response()
        google_put.return_value = final_response(metadata={"id": "animated", "name": "animation.gif", "mimeType": "image/gif"})
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(google_post.call_args.kwargs["json"]["name"], "animation.gif")
        self.assertEqual(google_put.call_args.kwargs["data"], original)
        with Image.open(io.BytesIO(google_put.call_args.kwargs["data"])) as uploaded:
            self.assertEqual(uploaded.n_frames, 2)

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_registered_raster_without_mime_uses_safe_octet_stream_and_preserves_bytes(self, google_post, google_put):
        self.photo.image.save("bitmap.bmp", ContentFile(image_bytes("BMP")), save=True)
        google_post.return_value = init_response()
        google_put.return_value = final_response(metadata={"id": "bitmap", "name": "bitmap.bmp", "mimeType": "application/octet-stream"})
        with patch.dict(Image.MIME, {"BMP": "application/octet-stream"}):
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(google_put.call_args.kwargs["data"], image_bytes("BMP"))
        self.assertEqual(google_put.call_args.kwargs["headers"]["Content-Type"], "application/octet-stream")

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_multipage_tiff_and_mpo_decoder_subtype_preserve_all_original_images(self, google_post, google_put):
        for format, suffix, mime_type in (("TIFF", ".tiff", "image/tiff"), ("MPO", ".mpo", "image/mpo")):
            with self.subTest(format=format):
                frames = [Image.new("RGB", (3, 3), color) for color in ("red", "green")]
                data = io.BytesIO()
                frames[0].save(data, format=format, save_all=True, append_images=frames[1:])
                original = data.getvalue()
                self.photo.image.save(f"pictures{suffix}", ContentFile(original), save=True)
                google_post.return_value = init_response()
                google_put.return_value = final_response(metadata={"id": "multiple-images", "name": f"pictures{suffix}", "mimeType": mime_type})
                response = self.upload()
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(google_put.call_args.kwargs["data"], original)
                with Image.open(io.BytesIO(google_put.call_args.kwargs["data"])) as uploaded:
                    self.assertEqual(uploaded.n_frames, 2)

    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_storage_file_is_closed_before_google_network_access(self, google_post):
        opened = []
        original_open = FileSystemStorage.open

        def track_open(storage, *args, **kwargs):
            handle = original_open(storage, *args, **kwargs)
            opened.append(handle)
            return handle

        def google_timeout(*args, **kwargs):
            self.assertTrue(opened)
            self.assertTrue(all(handle.closed for handle in opened))
            raise requests.Timeout(TOKEN)

        google_post.side_effect = google_timeout
        with patch.object(FileSystemStorage, "open", track_open):
            response = self.upload()
        self.assertEqual(response.status_code, 400)
        self.assertTrue(opened)
        self.assertTrue(all(handle.closed for handle in opened))
        self.assertNotIn(TOKEN, response.content.decode())


class DriveUploadTransportTests(SimpleTestCase):
    def upload(self):
        return GoogleDriveUploadService.upload(content=image_bytes(), mime_type="image/png", name="photo.png", access_token=TOKEN)

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_revoked_denied_redirected_or_server_failed_session_never_sends_file(self, google_post, google_put):
        for status in (401, 403, 404, 302, 429, 500):
            with self.subTest(status=status):
                response = init_response(status=status)
                google_post.return_value = response
                with self.assertRaises(ValidationError) as caught:
                    self.upload()
                self.assertNotIn(TOKEN, str(caught.exception))
                response.close.assert_called_once()
                google_put.assert_not_called()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_session_url_cannot_redirect_credentials_or_bytes_to_another_host_path_or_scheme(self, google_post, google_put):
        for location in (
            None, "http://www.googleapis.com/upload/drive/v3/files?upload_id=x",
            "https://evil.example/upload/drive/v3/files?upload_id=x",
            "https://www.googleapis.com.evil.example/upload/drive/v3/files?upload_id=x",
            "https://user@www.googleapis.com/upload/drive/v3/files?upload_id=x",
            "https://www.googleapis.com/other?upload_id=x",
            "https://www.googleapis.com/upload/drive/v3/files",
            SESSION_URL + "#fragment",
        ):
            with self.subTest(location=location):
                google_post.return_value = init_response(location=location)
                with self.assertRaises(ValidationError):
                    self.upload()
                google_put.assert_not_called()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_uncertain_completion_is_not_retried_and_never_echoes_google_body_or_token(self, google_post, google_put):
        for status in (401, 403, 404, 302, 308, 500):
            with self.subTest(status=status):
                google_post.reset_mock()
                google_put.reset_mock()
                google_post.return_value = init_response()
                google_put.return_value = final_response(status=status)
                with self.assertRaises(ValidationError) as caught:
                    self.upload()
                self.assertIn("Check My Drive", str(caught.exception))
                self.assertNotIn(TOKEN, str(caught.exception))
                google_post.assert_called_once()
                google_put.assert_called_once()
                google_put.return_value.iter_content.assert_not_called()
                google_put.return_value.close.assert_called_once()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_timeout_after_sending_bytes_has_safe_uncertain_message_and_no_replay(self, google_post, google_put):
        google_post.return_value = init_response()
        google_put.side_effect = requests.Timeout(f"secret {TOKEN}")
        with self.assertRaises(ValidationError) as caught:
            self.upload()
        self.assertIn("Check My Drive", str(caught.exception))
        self.assertNotIn(TOKEN, str(caught.exception))
        google_post.assert_called_once()
        google_put.assert_called_once()

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_success_requires_bounded_metadata_with_valid_id_mime_and_resource_key(self, google_post, google_put):
        for metadata in (
            {"id": "bad/id", "name": "photo.png", "mimeType": "image/png"},
            {"id": "uploaded", "name": "photo.png", "mimeType": "application/pdf"},
            {"id": "uploaded", "name": "", "mimeType": "image/png"},
            {"id": "uploaded", "name": "photo.png", "mimeType": "image/png", "resourceKey": "bad/key"},
        ):
            with self.subTest(metadata=metadata):
                google_post.return_value = init_response()
                google_put.return_value = final_response(metadata=metadata)
                with self.assertRaises(ValidationError):
                    self.upload()
        for content in (b"not JSON secret " + TOKEN.encode(), b"x" * (64 * 1024 + 1)):
            google_post.return_value = init_response()
            google_put.return_value = final_response()
            google_put.return_value.iter_content.return_value = iter([content])
            with self.assertRaises(ValidationError) as caught:
                self.upload()
            self.assertNotIn(TOKEN, str(caught.exception))

    @patch("apps.google_integration.drive_uploads.requests.put")
    @patch("apps.google_integration.drive_uploads.requests.post")
    def test_upload_resource_link_is_derived_from_verified_id_and_resource_key(self, google_post, google_put):
        google_post.return_value = init_response()
        google_put.return_value = final_response(metadata={
            "id": "uploaded", "name": "photo.png", "mimeType": "image/png", "resourceKey": "sharing-key",
            "webViewLink": "https://evil.example/private-url",
        })
        resource = self.upload()
        self.assertEqual(resource["url"], "https://drive.google.com/file/d/uploaded/view?resourcekey=sharing-key")
