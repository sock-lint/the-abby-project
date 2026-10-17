import logging
from urllib.parse import urlencode

from django.db import OperationalError
from django.http import HttpResponseRedirect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import get_child_or_404, child_not_found_response

from .drive import GoogleDriveSelectionSerializer, GoogleDriveService
from .drive_uploads import (
    AbbyDriveSourceService, GoogleDriveSourcePagination, GoogleDriveSourceQuerySerializer,
    GoogleDriveUploadSerializer, GoogleDriveUploadService,
)
from .models import GoogleAccount
from .services import GoogleAuthService
from . import oauth_exchange
from .throttling import GoogleOAuthThrottle

logger = logging.getLogger(__name__)


class GoogleDriveConfigView(APIView):
    """Public browser credentials, never stored account credentials."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(GoogleDriveService.picker_config())


class GoogleDriveFileView(APIView):
    """Validate a Picker selection and return canonical resource details."""

    permission_classes = [IsParent]

    def post(self, request):
        selection = GoogleDriveSelectionSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        GoogleDriveService.require_configured()
        metadata = GoogleDriveService.get_file(**selection.validated_data)
        return Response(GoogleDriveService.resource(metadata))


class GoogleDriveSourcesView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        query = GoogleDriveSourceQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        source_type = query.validated_data["source_type"]
        paginator = GoogleDriveSourcePagination()
        records = paginator.paginate_queryset(AbbyDriveSourceService.queryset(request.user, source_type), request, view=self)
        return paginator.get_paginated_response([AbbyDriveSourceService.describe(record, source_type) for record in records])


class GoogleDriveUploadView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        upload = GoogleDriveUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        GoogleDriveService.require_configured()
        content, mime_type, name = AbbyDriveSourceService.read(
            request.user, upload.validated_data["source_type"], upload.validated_data["source_id"],
        )
        resource = GoogleDriveUploadService.upload(
            content=content, mime_type=mime_type, name=name, access_token=upload.validated_data["access_token"],
        )
        return Response(resource, status=status.HTTP_201_CREATED)


# ── helpers ──────────────────────────────────────────────────────────────

def _target_user(request):
    """Resolve the target user from ?for_user=<id>.

    Parents can target a child; everyone else targets themselves.
    """
    for_user_id = request.query_params.get("for_user")
    if not for_user_id:
        return request.user, None

    if request.user.role != "parent":
        return None, Response(
            {"error": "Only parents can link accounts for children."},
            status=status.HTTP_403_FORBIDDEN,
        )

    child = get_child_or_404(for_user_id, requesting_user=request.user)
    if child is None:
        return None, child_not_found_response()
    return child, None


# OAuth returns carry only an opaque, browser-bound, one-use ticket.
class GoogleOAuthConfigView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"configured": GoogleAuthService.is_configured()})


def _exchange_error(exc):
    return Response({"error": str(exc), "code": exc.code}, status=getattr(exc, "http_status", 400))


class GoogleAuthInitView(APIView):
    throttle_classes = [GoogleOAuthThrottle]
    throttle_scope = "google_oauth"

    def get(self, request):
        if not GoogleAuthService.is_configured():
            return Response({"error": "Google OAuth is not configured."}, status=503)
        target, err = _target_user(request)
        if err:
            return err
        try:
            return Response(oauth_exchange.start(request, mode="link", target=target))
        except oauth_exchange.ExchangeError as exc:
            return _exchange_error(exc)


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [GoogleOAuthThrottle]
    throttle_scope = "google_oauth"

    def get(self, request):
        if not GoogleAuthService.is_configured():
            return Response({"error": "Google OAuth is not configured."}, status=503)
        try:
            return Response(oauth_exchange.start(request, mode="login"))
        except oauth_exchange.ExchangeError as exc:
            return _exchange_error(exc)


class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @staticmethod
    def redirect(*, state=None, ticket=None, error=None):
        params = {"google_exchange": ticket} if ticket else {"google_error": error}
        if state:
            params["google_state"] = state
        response = HttpResponseRedirect("/#" + urlencode(params))
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def get(self, request):
        state = request.query_params.get("state")
        claimed = oauth_exchange.claim_callback(state)
        if not claimed:
            return self.redirect(error="invalid_state")
        flow_id, provider_verifier = claimed
        code = request.query_params.get("code", "")
        error = None
        if request.query_params.get("error"):
            error = "denied"  # Never reflect Google's untrusted error text.
        elif not code or len(code) > 2048:
            error = "missing_code"
        if error:
            oauth_exchange.fail_callback(flow_id)
            return self.redirect(state=state, error=error)
        try:
            google_id, email, credentials = GoogleAuthService.exchange_code(code, provider_verifier)
            ticket = oauth_exchange.finish_callback(flow_id, google_id, email, credentials)
        except Exception:
            # Provider exceptions can embed authorization codes and credential bodies.
            logger.warning("Google OAuth provider exchange failed")
            oauth_exchange.fail_callback(flow_id)
            return self.redirect(state=state, error="token_exchange_failed")
        return self.redirect(state=state, ticket=ticket, error="invalid_exchange")


class GoogleExchangeView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [GoogleOAuthThrottle]
    throttle_scope = "google_oauth"

    def post(self, request):
        try:
            response = Response(oauth_exchange.exchange(request))
        except oauth_exchange.ExchangeError as exc:
            response = _exchange_error(exc)
        except oauth_exchange.AuthorizationBusy:
            response = _exchange_error(oauth_exchange.ExchangeError("authorization_changed"))
        except OperationalError as exc:
            if not oauth_exchange.is_lock_conflict(exc):
                raise
            response = _exchange_error(oauth_exchange.ExchangeError("authorization_changed"))
        response["Referrer-Policy"] = "no-referrer"
        response["Cache-Control"] = "no-store"
        return response


# ── Account management ───────────────────────────────────────────────────

class GoogleAccountView(APIView):
    """GET/DELETE /api/auth/google/account/"""

    def get(self, request):
        target, err = _target_user(request)
        if err:
            return err

        try:
            account = target.google_account
        except GoogleAccount.DoesNotExist:
            return Response({"linked": False})

        return Response({
            "linked": True,
            "google_email": account.google_email,
            "calendar_sync_enabled": account.calendar_sync_enabled,
            "calendar_id": account.calendar_id,
        })

    def delete(self, request):
        target, err = _target_user(request)
        if err:
            return err

        GoogleAuthService.unlink_account(target)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Calendar settings ────────────────────────────────────────────────────

class CalendarSettingsView(APIView):
    """GET/PATCH /api/auth/google/calendar/"""

    def get(self, request):
        try:
            account = request.user.google_account
        except GoogleAccount.DoesNotExist:
            return Response(
                {"error": "No linked Google account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "calendar_sync_enabled": account.calendar_sync_enabled,
            "calendar_id": account.calendar_id,
        })

    def patch(self, request):
        try:
            account = request.user.google_account
        except GoogleAccount.DoesNotExist:
            return Response(
                {"error": "No linked Google account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if "calendar_sync_enabled" in request.data:
            account.calendar_sync_enabled = bool(request.data["calendar_sync_enabled"])
        if "calendar_id" in request.data:
            account.calendar_id = request.data["calendar_id"]

        account.save(update_fields=["calendar_sync_enabled", "calendar_id", "updated_at"])
        return Response({
            "calendar_sync_enabled": account.calendar_sync_enabled,
            "calendar_id": account.calendar_id,
        })


# ── Manual sync ──────────────────────────────────────────────────────────

class CalendarSyncView(APIView):
    """POST /api/auth/google/calendar/sync/ — trigger a full resync."""

    def post(self, request):
        try:
            account = request.user.google_account
        except GoogleAccount.DoesNotExist:
            return Response(
                {"error": "No linked Google account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not account.calendar_sync_enabled:
            return Response(
                {"error": "Calendar sync is not enabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .tasks import full_sync_task

        full_sync_task.delay(request.user.id)
        return Response({"status": "sync_queued"})
