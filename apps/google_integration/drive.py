"""Selected-file Drive access using short-lived Picker tokens.

Tokens belong to one browser interaction. They never enter GoogleAccount,
the ingestion job, or a Celery payload. Only Google API URLs are fetched.
"""
from __future__ import annotations

import json
import re
import tempfile

import requests
from django.conf import settings
from django.core.files import File
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
DRIVE_API_ROOT = "https://www.googleapis.com/drive/v3/files/"
DRIVE_TIMEOUT = (5, 30)
FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class GoogleDriveSelectionSerializer(serializers.Serializer):
    file_id = serializers.RegexField(FILE_ID_PATTERN, max_length=256)
    access_token = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)
    resource_key = serializers.RegexField(FILE_ID_PATTERN, max_length=256, required=False)

    def validate_access_token(self, value):
        # Disallow whitespace/control characters before constructing a header.
        if not all(33 <= ord(character) <= 126 for character in value):
            raise serializers.ValidationError("Invalid Google access token.")
        return value


def _error(message):
    return ValidationError({"error": message})


class GoogleDriveService:
    @staticmethod
    def picker_config():
        values = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "api_key": settings.GOOGLE_PICKER_API_KEY,
            "app_id": settings.GOOGLE_PICKER_APP_ID,
        }
        configured = all(values.values())
        return {"configured": configured, **(values if configured else dict.fromkeys(values, ""))}

    @classmethod
    def require_configured(cls):
        if not cls.picker_config()["configured"]:
            raise _error("Google Drive file picker is not configured.")

    @staticmethod
    def _request(file_id, access_token, params, resource_key=None):
        headers = {"Authorization": f"Bearer {access_token}"}
        if resource_key:
            headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        try:
            response = requests.get(
                DRIVE_API_ROOT + file_id,
                params={"supportsAllDrives": "true", **params},
                headers=headers,
                timeout=DRIVE_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException:
            # Google/requests errors can include credentials. Never echo/log them.
            raise _error("Google Drive could not be reached. Please try again.") from None
        if response.status_code != 200:
            response.close()
            if response.status_code in (401, 403, 404):
                raise _error("Google Drive could not open this file. Choose it again and allow access.")
            raise _error("Google Drive could not retrieve this file. Please try again.")
        return response

    @classmethod
    def get_file(cls, file_id, access_token, resource_key=None):
        response = cls._request(file_id, access_token, {
            "fields": "id,name,mimeType,size,trashed,capabilities(canDownload),resourceKey",
        }, resource_key=resource_key)
        try:
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_METADATA_BYTES:
                    raise _error("Google Drive returned invalid file details.")
            metadata = json.loads(content)
        except (ValueError, requests.RequestException):
            raise _error("Google Drive could not read this file's details. Please try again.") from None
        finally:
            response.close()
        if (
            not isinstance(metadata, dict)
            or metadata.get("id") != file_id
            or not isinstance(metadata.get("name"), str)
            or not metadata["name"].strip()
            or not isinstance(metadata.get("mimeType"), str)
            or not metadata["mimeType"]
            or len(metadata["mimeType"]) > 200
            or metadata.get("trashed")
        ):
            raise _error("Google Drive returned an unavailable file.")
        if metadata["mimeType"] in (
            "application/vnd.google-apps.folder", "application/vnd.google-apps.shortcut",
        ):
            raise _error("Choose a file rather than a folder or shortcut.")
        resolved_key = metadata.get("resourceKey") or resource_key
        if resolved_key:
            if not isinstance(resolved_key, str) or not FILE_ID_PATTERN.fullmatch(resolved_key):
                raise _error("Google Drive returned invalid file details.")
            metadata["resourceKey"] = resolved_key
        return metadata

    @staticmethod
    def resource(metadata):
        file_id = metadata["id"]
        # Derive the link from the validated ID; never trust a browser URL.
        url = f"https://drive.google.com/file/d/{file_id}/view"
        workspace_paths = {
            "application/vnd.google-apps.document": "document",
            "application/vnd.google-apps.spreadsheet": "spreadsheets",
            "application/vnd.google-apps.presentation": "presentation",
        }
        workspace_path = workspace_paths.get(metadata["mimeType"])
        if workspace_path:
            url = f"https://docs.google.com/{workspace_path}/d/{file_id}/edit"
        if metadata.get("resourceKey"):
            url += f"?resourcekey={metadata['resourceKey']}"
        resource_type = "link"
        if metadata["mimeType"] == "application/pdf" or workspace_path:
            resource_type = "doc"
        elif metadata["mimeType"].startswith("image/"):
            resource_type = "image"
        elif metadata["mimeType"].startswith("video/"):
            resource_type = "video"
        return {
            "id": file_id,
            "title": metadata["name"].strip()[:200],
            "url": url,
            "mime_type": metadata["mimeType"],
            "resource_type": resource_type,
        }

    @classmethod
    def download_pdf(cls, file_id, access_token, resource_key=None):
        metadata = cls.get_file(file_id, access_token, resource_key=resource_key)
        if metadata["mimeType"] != "application/pdf":
            raise _error("Choose a PDF file. Google Docs exports are not supported.")
        if not isinstance(metadata.get("capabilities"), dict) or not metadata["capabilities"].get("canDownload"):
            raise _error("Google Drive does not allow this PDF to be downloaded.")
        try:
            file_size = int(metadata["size"])
        except (KeyError, ValueError, TypeError):
            raise _error("Google Drive returned an invalid PDF size.") from None
        if file_size < 0 or file_size > MAX_PDF_BYTES:
            raise _error("Choose a PDF no larger than 25 MB.")

        response = cls._request(file_id, access_token, {"alt": "media"}, resource_key=metadata.get("resourceKey"))
        copied = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
        try:
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise _error("Choose a PDF no larger than 25 MB.")
                copied.write(chunk)
            copied.seek(0)
            if copied.read(5) != b"%PDF-":
                raise _error("The selected file does not contain a valid PDF.")
            copied.seek(0)
            return cls.resource(metadata), File(copied, name=f"drive-{file_id}.pdf")
        except requests.RequestException:
            copied.close()
            raise _error("Google Drive could not download this PDF. Please try again.") from None
        except Exception:
            copied.close()
            raise
        finally:
            response.close()
