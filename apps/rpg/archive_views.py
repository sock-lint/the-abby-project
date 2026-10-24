"""Shared native archive/restore API over the same receipt service as MCP."""
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsStaffParent

from .authoring_archive import (
    AuthoringArchiveConflict, AuthoringArchiveRequestConflict, list_authoring, set_archived,
)
from .content.editorial import get_editorial_draft, list_editorial_drafts
from .content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from .content.loader import ContentPackError


class _Conflict(APIException):
    status_code = 409


def list_options(request, *, published=False):
    allowed = {"include_archived", "after", "limit", "_abby_session", "_abby_retry"}
    if published:
        allowed.add("published")
    if set(request.query_params) - allowed:
        raise ValidationError({"detail": "Only archive, cursor and limit selectors are accepted."})
    result = {}
    for field in ("include_archived", "published"):
        if field in request.query_params:
            if request.query_params[field] not in {"true", "false"}:
                raise ValidationError({"detail": f"{field} must be true or false."})
            result[field] = request.query_params[field] == "true"
    if "limit" in request.query_params:
        try:
            result["limit"] = int(request.query_params["limit"])
        except ValueError:
            raise ValidationError({"detail": "limit must be an integer from 1 to 100."}) from None
    if "after" in request.query_params:
        result["after"] = request.query_params["after"]
    return result


class _AuthoringView(APIView):
    permission_classes = [IsAuthenticated, IsStaffParent]

    def handle_exception(self, exc):
        if isinstance(exc, AuthoringArchiveConflict):
            code = "idempotency_conflict" if isinstance(exc, AuthoringArchiveRequestConflict) else "authoring_archive_conflict"
            exc = _Conflict({"detail": str(exc), "code": code})
        elif isinstance(exc, ContentAuthorPermissionDenied):
            exc = PermissionDenied("Authoring requires an active staff parent in the current family.")
        elif isinstance(exc, ContentObjectNotFound):
            exc = NotFound("Authoring record not found for this author and family.")
        elif isinstance(exc, ContentPackError):
            exc = ValidationError({"detail": str(exc)})
        return super().handle_exception(exc)


class AuthoringArchiveView(_AuthoringView):
    kind = None

    def post(self, request, object_id):
        if set(request.query_params) - {"_abby_session", "_abby_retry"}:
            raise ValidationError({"detail": "Archive accepts no account or query selectors."})
        required = {"revision", "is_archived", "request_id", "confirmation"}
        if not isinstance(request.data, dict) or set(request.data) != required:
            raise ValidationError({"detail": "Supply revision, is_archived, request_id and confirmation."})
        return Response(set_archived(request.user, self.kind, object_id, **request.data))


class EditorialDraftListView(_AuthoringView):
    def get(self, request):
        return Response(list_editorial_drafts(request.user, **list_options(request)))


class EditorialDraftDetailView(_AuthoringView):
    def get(self, request, draft_id):
        if set(request.query_params) - {"_abby_session", "_abby_retry"}:
            raise ValidationError({"detail": "Draft reads accept no account or query selectors."})
        return Response(get_editorial_draft(request.user, draft_id))


def content_draft_page(request):
    page = list_authoring(request.user, "content", **list_options(request, published=True))
    return {"drafts": page.pop("rows"), **page}
