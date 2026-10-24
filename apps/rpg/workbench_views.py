"""Staff-parent content authoring with private drafts and explicit publication."""
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.permissions import IsStaffParent

from .archive_views import content_draft_page
from .authoring_archive import AuthoringArchiveConflict
from .content.errors import ContentAuthorPermissionDenied
from .content.loader import ContentPackError
from .content.workbench import (
    WorkbenchConflict, WorkbenchNotFound, create_draft, describe_workbench, get_draft, preview_draft,
    publish_draft, save_draft, simulate_draft,
)


class _Conflict(APIException):
    status_code = 409
    default_code = "content_workbench_conflict"


class WorkbenchSimulationThrottle(UserRateThrottle):
    scope = "content_workbench_simulation"
    rate = "5/min"


def _body(request, required, optional=()):
    value = request.data
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - value.keys():
        raise ValidationError({"detail": f"Supply exactly {', '.join(required)}" +
            (f" (optional: {', '.join(optional)})" if optional else "") + "."})
    return value


class _WorkbenchView(APIView):
    permission_classes = [IsAuthenticated, IsStaffParent]

    allowed_query = set()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if set(request.query_params) - {"_abby_session", "_abby_retry"} - self.allowed_query:
            raise ValidationError({"detail": "Content Workbench accepts no account or query selectors."})

    def handle_exception(self, exc):
        if isinstance(exc, ContentAuthorPermissionDenied):
            exc = PermissionDenied("Authoring requires an active staff parent in the current family.")
        elif isinstance(exc, (WorkbenchConflict, AuthoringArchiveConflict)):
            exc = _Conflict({"detail": str(exc)})
        elif isinstance(exc, WorkbenchNotFound):
            exc = NotFound({"detail": str(exc)})
        elif isinstance(exc, (ContentPackError, ValueError)):
            exc = ValidationError({"detail": str(exc)})
        return super().handle_exception(exc)


class ContentWorkbenchView(_WorkbenchView):
    def get(self, request):
        return Response(describe_workbench(request.user))


class ContentDraftListView(_WorkbenchView):
    allowed_query = {"include_archived", "after", "limit", "published"}

    def get(self, request):
        return Response(content_draft_page(request))

    def post(self, request):
        data = _body(request, ("name",))
        return Response(create_draft(request.user, data["name"]), status=201)


class ContentDraftDetailView(_WorkbenchView):
    def get(self, request, draft_id):
        return Response(get_draft(request.user, draft_id))

    def patch(self, request, draft_id):
        data = _body(request, ("revision", "changes"), ("name",))
        return Response(save_draft(request.user, draft_id, data["revision"], data["changes"], name=data.get("name")))


class ContentDraftPreviewView(_WorkbenchView):
    def post(self, request, draft_id):
        data = _body(request, ("revision",))
        return Response(preview_draft(request.user, draft_id, data["revision"]))


class ContentDraftSimulationView(_WorkbenchView):
    throttle_classes = [WorkbenchSimulationThrottle]

    def post(self, request, draft_id):
        data = _body(request, ("revision", "preview_id", "config"))
        return Response(simulate_draft(request.user, draft_id, data["revision"], data["preview_id"], data["config"]))


class ContentDraftPublishView(_WorkbenchView):
    def post(self, request, draft_id):
        data = _body(request, ("revision", "preview_id", "content_digest", "confirmation"))
        if data["confirmation"] is not True:
            raise ValidationError({"detail": "Explicit confirmation is required to publish global catalog changes."})
        return Response(publish_draft(request.user, draft_id, data["revision"], data["preview_id"], data["content_digest"]))
