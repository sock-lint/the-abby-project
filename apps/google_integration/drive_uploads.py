"""Export authorized Abby files directly from storage to the parent's My Drive."""
from __future__ import annotations

import io
import json
import mimetypes
import warnings
from collections.abc import Mapping
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import requests
from django.shortcuts import get_object_or_404
from PIL import Image
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination

from config.viewsets import filter_queryset_by_role, filter_resources_under_accessible_projects

from .drive import FILE_ID_PATTERN, MAX_METADATA_BYTES, GoogleDriveService, GoogleDriveTokenSerializer


SOURCE_TYPES = ("ingestion_pdf", "project_photo", "homework_proof", "creation_photo")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
UPLOAD_TIMEOUT = (5, 60)
UPLOAD_UNCERTAIN = "Google Drive may have saved this file. Check My Drive before trying again."
PREFERRED_IMAGE_SUFFIXES = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tiff"}
NON_RASTER_FORMATS = {"EPS", "PDF", "WMF", "MPEG"}


def _error(message):
    return ValidationError({"error": message})


def _image_details(image_format, filename):
    """Derive content type and filename suffix from Pillow's decoded format.

    Some valid, less common raster plugins have no registered MIME type. Drive
    accepts their original bytes as octet-stream; never invent a type from an
    unverified filename or convert an animation/multi-page image to one frame.
    """
    Image.init()
    # A decoder can return a registered subtype such as MPO through JPEG's
    # opener, so Image.OPEN alone is not the set of valid decoded formats.
    if not isinstance(image_format, str) or image_format in NON_RASTER_FORMATS:
        raise _error("The saved image format is not supported for Drive export.")
    extensions = Image.registered_extensions()
    suffix = PurePosixPath(filename).suffix.lower()
    if extensions.get(suffix) != image_format:
        suffix = PREFERRED_IMAGE_SUFFIXES.get(image_format) or next(
            (extension for extension, format_name in extensions.items() if format_name == image_format), None,
        )
    if not suffix:
        raise _error("The saved image format is not supported for Drive export.")
    mime_type = Image.MIME.get(image_format) or mimetypes.guess_type(f"photo{suffix}")[0]
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "application/octet-stream"
    return mime_type, suffix


class GoogleDriveSourceQuerySerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=SOURCE_TYPES)


class GoogleDriveUploadSerializer(GoogleDriveTokenSerializer):
    source_type = serializers.ChoiceField(choices=SOURCE_TYPES)
    source_id = serializers.CharField(max_length=64, trim_whitespace=False)

    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise _error("Select a saved Abby file. URLs, storage paths, and file uploads are not accepted.")
        return super().to_internal_value(data)

    def validate(self, attrs):
        source_id = attrs["source_id"]
        try:
            if attrs["source_type"] == "ingestion_pdf":
                attrs["source_id"] = UUID(source_id)
            else:
                if not source_id.isascii() or not source_id.isdigit() or len(source_id) > 18 or int(source_id) < 1:
                    raise ValueError
                attrs["source_id"] = int(source_id)
        except ValueError:
            raise serializers.ValidationError({"source_id": "Select a valid Abby file."}) from None
        return attrs


class GoogleDriveSourcePagination(PageNumberPagination):
    page_size = 20

    @staticmethod
    def _relative(link):
        if link is None:
            return None
        parsed = urlsplit(link)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    def get_next_link(self):
        return self._relative(super().get_next_link())

    def get_previous_link(self):
        return self._relative(super().get_previous_link())


class AbbyDriveSourceService:
    """Each category preserves the existing owner's API visibility boundary."""

    @staticmethod
    def queryset(user, source_type):
        if source_type == "ingestion_pdf":
            from apps.ingestion.models import ProjectIngestionJob

            queryset = ProjectIngestionJob.objects.filter(created_by=user, source_type="pdf").exclude(status="discarded")
            file_field = "source_file"
            ordering = ("-created_at", "-pk")
        elif source_type == "project_photo":
            from apps.portfolio.models import ProjectPhoto

            queryset = filter_resources_under_accessible_projects(
                user, ProjectPhoto.objects.select_related("project"),
            )
            file_field = "image"
            ordering = ("-uploaded_at", "-pk")
        elif source_type == "homework_proof":
            from apps.homework.models import HomeworkProof

            queryset = filter_queryset_by_role(
                user, HomeworkProof.objects.filter(submission__status="approved").select_related("submission__assignment"),
                role_filter_field="submission__user",
            )
            file_field = "image"
            ordering = ("-created_at", "-pk")
        elif source_type == "creation_photo":
            from apps.creations.models import Creation

            queryset = filter_queryset_by_role(user, Creation.objects.select_related("user"))
            file_field = "image"
            ordering = ("-created_at", "-pk")
        else:
            raise _error("Select a supported Abby file category.")
        return queryset.exclude(**{file_field: ""}).exclude(**{f"{file_field}__isnull": True}).order_by(*ordering)

    @staticmethod
    def file_field(record, source_type):
        return record.source_file if source_type == "ingestion_pdf" else record.image

    @classmethod
    def describe(cls, record, source_type):
        filename = PurePosixPath(cls.file_field(record, source_type).name).name
        title = getattr(record, "caption", "") or filename
        if source_type == "ingestion_pdf":
            draft = record.result_json if isinstance(record.result_json, dict) else {}
            context = draft.get("title") if isinstance(draft.get("title"), str) else "Imported PDF"
        elif source_type == "project_photo":
            context = record.project.title
        elif source_type == "homework_proof":
            context = record.submission.assignment.title
        else:
            context = record.user.display_label
        mime_type = "application/pdf" if source_type == "ingestion_pdf" else mimetypes.guess_type(filename)[0]
        return {
            "source_type": source_type, "source_id": str(record.pk), "title": title[:200],
            "mime_type": mime_type if (mime_type and mime_type.startswith("image/")) or source_type == "ingestion_pdf" else "image/*",
            "context": (context or "Imported PDF")[:200],
        }

    @classmethod
    def read(cls, user, source_type, source_id):
        record = get_object_or_404(cls.queryset(user, source_type), pk=source_id)
        stored_file = cls.file_field(record, source_type)
        # Resolve a model-owned key only. Reject damaged/legacy pointers outside
        # the category's upload directory rather than reading arbitrary paths.
        prefix = {"ingestion_pdf": "ingestion/", "project_photo": "portfolio/", "homework_proof": "homework_proofs/", "creation_photo": "creations/"}[source_type]
        path = PurePosixPath(stored_file.name)
        if not stored_file.name.startswith(prefix) or "\\" in stored_file.name or ".." in path.parts:
            raise NotFound("The saved Abby file is unavailable.")
        try:
            if stored_file.size > MAX_UPLOAD_BYTES:
                raise _error("Choose an Abby file no larger than 25 MB.")
            with stored_file.open("rb") as source:
                content = source.read(MAX_UPLOAD_BYTES + 1)
        except ValidationError:
            raise
        except Exception:
            # Storage errors can include signed URLs or private bucket paths.
            raise _error("The saved Abby file could not be read. Please try again.") from None
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise _error("Choose a nonempty Abby file no larger than 25 MB.")
        if source_type == "ingestion_pdf":
            if not content.startswith(b"%PDF-"):
                raise _error("The saved file does not contain a valid PDF.")
            try:
                import pdfplumber

                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    if not pdf.pages:
                        raise ValueError
            except Exception:
                raise _error("The saved file does not contain a readable PDF.") from None
            mime_type, suffix = "application/pdf", ".pdf"
        else:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(content)) as image:
                        mime_type, suffix = _image_details(image.format, path.name)
                        image.verify()
            except ValidationError:
                raise
            except Exception:
                raise _error("The saved file does not contain a readable photo.") from None
        # Use the stored basename, with an extension matching verified content.
        name = path.name[:190]
        name = str(PurePosixPath(name).with_suffix(suffix))
        return content, mime_type, name


class GoogleDriveUploadService:
    @staticmethod
    def _metadata(response):
        try:
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_METADATA_BYTES:
                    raise ValueError
            return json.loads(content)
        except (ValueError, requests.RequestException):
            raise _error(UPLOAD_UNCERTAIN) from None

    @staticmethod
    def _session_url(location):
        if not isinstance(location, str):
            raise _error("Google Drive could not start the upload. Please try again.")
        try:
            parsed = urlsplit(location)
            valid = (
                parsed.scheme == "https" and parsed.netloc == "www.googleapis.com"
                and parsed.path == "/upload/drive/v3/files" and not parsed.fragment
                and bool(parse_qs(parsed.query).get("upload_id"))
            )
        except ValueError:
            valid = False
        if not valid:
            raise _error("Google Drive could not start the upload. Please try again.")
        return location

    @classmethod
    def upload(cls, *, content, mime_type, name, access_token):
        # Resumable sessions support the full 25 MB limit. Complete in one PUT;
        # never retry automatically or persist the session URL/Google token.
        try:
            response = requests.post(
                UPLOAD_URL,
                params={"uploadType": "resumable", "fields": "id,name,mimeType,resourceKey"},
                json={"name": name, "mimeType": mime_type},
                headers={
                    "Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": mime_type, "X-Upload-Content-Length": str(len(content)),
                },
                allow_redirects=False, timeout=UPLOAD_TIMEOUT, stream=True,
            )
        except requests.RequestException:
            raise _error("Google Drive could not start the upload. Please try again.") from None
        try:
            if response.status_code != 200:
                raise _error("Google Drive did not allow this upload. Reconnect to Google and try again.")
            session_url = cls._session_url(response.headers.get("Location"))
        finally:
            response.close()
        try:
            response = requests.put(
                session_url, data=content,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": mime_type, "Content-Length": str(len(content))},
                allow_redirects=False, timeout=UPLOAD_TIMEOUT, stream=True,
            )
        except requests.RequestException:
            raise _error(UPLOAD_UNCERTAIN) from None
        try:
            if response.status_code not in (200, 201):
                raise _error(UPLOAD_UNCERTAIN)
            metadata = cls._metadata(response)
            if (
                not isinstance(metadata, dict) or not isinstance(metadata.get("id"), str)
                or not FILE_ID_PATTERN.fullmatch(metadata["id"])
                or not isinstance(metadata.get("name"), str) or not metadata["name"].strip()
                or metadata.get("mimeType") != mime_type
            ):
                raise _error(UPLOAD_UNCERTAIN)
            resource_key = metadata.get("resourceKey")
            if resource_key and (not isinstance(resource_key, str) or not FILE_ID_PATTERN.fullmatch(resource_key)):
                raise _error(UPLOAD_UNCERTAIN)
            return GoogleDriveService.resource(metadata)
        finally:
            response.close()
