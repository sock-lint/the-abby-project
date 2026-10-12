"""Selected-file authorization, canonical resources, and bounded PDF copies."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from apps.google_integration.drive import GoogleDriveService
from apps.google_integration.models import GoogleAccount
from apps.google_integration.services import GoogleAuthService
from config.tests.base import BaseFamilyAPITestCase


PICKER_SETTINGS = {
    "GOOGLE_CLIENT_ID": "synthetic-client.apps.googleusercontent.com",
    "GOOGLE_PICKER_API_KEY": "synthetic-picker-key",
    "GOOGLE_PICKER_APP_ID": "123456789012",
    "GOOGLE_CLIENT_SECRET": "synthetic-server-secret",
}
SELECTION = {"file_id": "school-pdf-1", "access_token": "synthetic-transient-token"}
METADATA = {
    "id": "school-pdf-1", "name": "Science worksheet.pdf", "mimeType": "application/pdf",
    "size": "9", "trashed": False, "capabilities": {"canDownload": True},
}


def drive_response(*, metadata=None, chunks=None, status=200):
    response = Mock()
    response.status_code = status
    response.iter_content.return_value = iter(
        chunks if chunks is not None else [json.dumps(metadata or METADATA).encode()]
    )
    return response


def contract_fixture(name):
    return json.loads((Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures" / name).read_text())


@override_settings(**PICKER_SETTINGS)
class DriveViewsTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "drive-parent"}]
    family_children = [{"username": "drive-child"}]

    def setUp(self):
        self.client.force_authenticate(self.parents[0])

    def test_config_is_public_and_matches_shared_fixture_without_server_secrets(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/auth/google/drive/config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), contract_fixture("google-drive-config.json"))
        self.assertNotIn("secret", response.content.decode())

    def test_config_is_unconfigured_until_all_browser_values_are_present(self):
        for missing_setting in ("GOOGLE_CLIENT_ID", "GOOGLE_PICKER_API_KEY", "GOOGLE_PICKER_APP_ID"):
            with self.subTest(missing_setting=missing_setting), override_settings(**{missing_setting: ""}):
                response = self.client.get("/api/auth/google/drive/config/")
                self.assertEqual(response.json(), {
                    "configured": False, "client_id": "", "api_key": "", "app_id": "",
                })

    @patch("apps.google_integration.drive.requests.get")
    def test_only_parent_can_resolve_file(self, google_get):
        for user, status_code in ((None, 401), (self.children[0], 403)):
            with self.subTest(user=user):
                self.client.force_authenticate(user=user)
                response = self.client.post("/api/auth/google/drive/file/", SELECTION, format="json")
                self.assertEqual(response.status_code, status_code)
        google_get.assert_not_called()

    @patch("apps.google_integration.drive.requests.get")
    def test_invalid_selection_cannot_start_google_request(self, google_get):
        invalid = (
            {}, {**SELECTION, "file_id": "../admin"}, {**SELECTION, "file_id": "a" * 257},
            {**SELECTION, "access_token": ""}, {**SELECTION, "access_token": "a" * 4097},
            {**SELECTION, "access_token": "injected\r\nheader"},
            {**SELECTION, "resource_key": "bad/key"},
        )
        for selection in invalid:
            with self.subTest(selection=selection):
                response = self.client.post("/api/auth/google/drive/file/", selection, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(SELECTION["access_token"], response.content.decode())
        google_get.assert_not_called()

    @patch("apps.google_integration.drive.requests.get")
    def test_unconfigured_picker_rejects_file_resolution(self, google_get):
        with override_settings(GOOGLE_PICKER_APP_ID=""):
            response = self.client.post("/api/auth/google/drive/file/", SELECTION, format="json")
        self.assertEqual(response.status_code, 400)
        google_get.assert_not_called()

    @patch("apps.google_integration.drive.requests.get")
    def test_file_metadata_is_canonical_and_never_reuses_calendar_credentials(self, google_get):
        account = GoogleAuthService.link_account(
            self.parents[0], "synthetic-google-parent", "parent@example.invalid",
            {"token": "synthetic-calendar-token", "refresh_token": "synthetic-calendar-refresh"},
        )
        encrypted_before = bytes(account.encrypted_credentials)
        google_get.return_value = drive_response()
        response = self.client.post("/api/auth/google/drive/file/", {
            **SELECTION, "title": "Untrusted title", "url": "https://evil.example.invalid",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), contract_fixture("google-drive-file.json"))
        account.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), encrypted_before)
        self.assertEqual(GoogleAccount.objects.count(), 1)
        call = google_get.call_args
        self.assertEqual(call.args, ("https://www.googleapis.com/drive/v3/files/school-pdf-1",))
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer synthetic-transient-token")
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(call.kwargs["timeout"], (5, 30))
        self.assertNotIn(SELECTION["access_token"], response.content.decode())

    @patch("apps.google_integration.drive.requests.get")
    def test_revoked_missing_or_inaccessible_file_returns_safe_error(self, google_get):
        for status_code in (401, 403, 404, 429, 503, 302):
            with self.subTest(status_code=status_code):
                google_get.return_value = drive_response(status=status_code)
                response = self.client.post("/api/auth/google/drive/file/", SELECTION, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(SELECTION["access_token"], response.content.decode())
                google_get.return_value.iter_content.assert_not_called()
                google_get.return_value.close.assert_called_once()

    @patch("apps.google_integration.drive.requests.get")
    def test_transport_errors_never_expose_token(self, google_get):
        google_get.side_effect = requests.Timeout(f"Network error with {SELECTION['access_token']}")
        response = self.client.post("/api/auth/google/drive/file/", SELECTION, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SELECTION["access_token"], response.content.decode())


class DriveFileTests(SimpleTestCase):
    @patch("apps.google_integration.drive.requests.get")
    def test_shared_resource_key_is_forwarded_and_canonical_metadata_key_is_preserved(self, google_get):
        google_get.side_effect = [
            drive_response(metadata={**METADATA, "resourceKey": "canonical-key"}),
            drive_response(chunks=[b"%PDF-1.7\n"]),
        ]
        resource, copied = GoogleDriveService.download_pdf(**SELECTION, resource_key="picker-key")
        with copied:
            self.assertEqual(copied.read(), b"%PDF-1.7\n")
        self.assertEqual(resource["url"], "https://drive.google.com/file/d/school-pdf-1/view?resourcekey=canonical-key")
        self.assertEqual(
            google_get.call_args_list[0].kwargs["headers"]["X-Goog-Drive-Resource-Keys"],
            "school-pdf-1/picker-key",
        )
        self.assertEqual(
            google_get.call_args_list[1].kwargs["headers"]["X-Goog-Drive-Resource-Keys"],
            "school-pdf-1/canonical-key",
        )

    @patch("apps.google_integration.drive.requests.get")
    def test_shared_key_is_retained_when_metadata_omits_it(self, google_get):
        google_get.return_value = drive_response()
        metadata = GoogleDriveService.get_file(**SELECTION, resource_key="picker-key")
        self.assertTrue(GoogleDriveService.resource(metadata)["url"].endswith("?resourcekey=picker-key"))

    @patch("apps.google_integration.drive.requests.get")
    def test_non_pdf_and_non_downloadable_pdf_are_rejected_before_media_download(self, google_get):
        invalid = (
            {**METADATA, "mimeType": "application/vnd.google-apps.document"},
            {**METADATA, "capabilities": {"canDownload": False}},
            {**METADATA, "size": str(25 * 1024 * 1024 + 1)},
            {**METADATA, "size": "unknown"},
        )
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                google_get.reset_mock()
                google_get.return_value = drive_response(metadata=metadata)
                with self.assertRaises(ValidationError):
                    GoogleDriveService.download_pdf(**SELECTION)
                self.assertEqual(google_get.call_count, 1)

    @patch("apps.google_integration.drive.requests.get")
    def test_actual_pdf_bytes_are_bounded_even_when_metadata_understates_size(self, google_get):
        media = drive_response(chunks=[b"%PDF-1.7", b"overflow"])
        google_get.side_effect = [drive_response(metadata={**METADATA, "size": "5"}), media]
        with patch("apps.google_integration.drive.MAX_PDF_BYTES", 8), self.assertRaises(ValidationError):
            GoogleDriveService.download_pdf(**SELECTION)
        media.close.assert_called_once()

    @patch("apps.google_integration.drive.requests.get")
    def test_pdf_mime_cannot_disguise_non_pdf_content(self, google_get):
        media = drive_response(chunks=[b"<html>not a PDF</html>"])
        google_get.side_effect = [drive_response(), media]
        with self.assertRaises(ValidationError):
            GoogleDriveService.download_pdf(**SELECTION)
        media.close.assert_called_once()

    @patch("apps.google_integration.drive.requests.get")
    def test_download_transport_error_is_safe_and_response_is_closed(self, google_get):
        media = drive_response(chunks=[])
        media.iter_content.side_effect = requests.ConnectionError(SELECTION["access_token"])
        google_get.side_effect = [drive_response(), media]
        with self.assertRaises(ValidationError) as caught:
            GoogleDriveService.download_pdf(**SELECTION)
        self.assertNotIn(SELECTION["access_token"], str(caught.exception))
        media.close.assert_called_once()

    @patch("apps.google_integration.drive.requests.get")
    def test_malformed_or_unavailable_metadata_is_rejected(self, google_get):
        invalid = (
            {**METADATA, "id": "another-file"}, {**METADATA, "name": ""},
            {**METADATA, "trashed": True}, {**METADATA, "mimeType": None},
            {**METADATA, "mimeType": "application/vnd.google-apps.folder"},
            {**METADATA, "mimeType": "application/vnd.google-apps.shortcut"},
            {**METADATA, "resourceKey": "bad/key"},
        )
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                google_get.return_value = drive_response(metadata=metadata)
                with self.assertRaises(ValidationError):
                    GoogleDriveService.get_file(**SELECTION)
        google_get.return_value = drive_response(chunks=[b"not JSON"])
        with self.assertRaises(ValidationError):
            GoogleDriveService.get_file(**SELECTION)

    @patch("apps.google_integration.drive.requests.get")
    def test_metadata_response_is_bounded(self, google_get):
        google_get.return_value = drive_response(chunks=[b"x" * (64 * 1024 + 1)])
        with self.assertRaises(ValidationError):
            GoogleDriveService.get_file(**SELECTION)

    def test_resource_types_match_existing_project_resource_choices(self):
        for mime_type, expected_type in (
            ("application/pdf", "doc"), ("application/vnd.google-apps.document", "doc"),
            ("application/vnd.google-apps.spreadsheet", "doc"),
            ("application/vnd.google-apps.presentation", "doc"),
            ("image/png", "image"), ("video/mp4", "video"), ("application/zip", "link"),
        ):
            with self.subTest(mime_type=mime_type):
                resource = GoogleDriveService.resource({**METADATA, "mimeType": mime_type})
                self.assertEqual(resource["resource_type"], expected_type)
