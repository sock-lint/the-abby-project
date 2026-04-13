import secrets

from django.core.cache import cache
from django.http import HttpResponseRedirect
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import get_child_or_404, child_not_found_response

from .models import GoogleAccount
from .services import GoogleAuthService


# ── helpers ──────────────────────────────────────────────────────────────

def _cache_key(state):
    return f"google_oauth_state:{state}"


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

    child = get_child_or_404(for_user_id)
    if child is None:
        return None, child_not_found_response()
    return child, None


# ── OAuth initiation (authenticated — linking) ──────────────────────────

class GoogleAuthInitView(APIView):
    """GET /api/auth/google/ — start OAuth for account linking.

    Optional query param: ?for_user=<child_id> (parent only).
    """

    def get(self, request):
        if not GoogleAuthService.is_configured():
            return Response(
                {"error": "Google OAuth is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        target, err = _target_user(request)
        if err:
            return err

        state = secrets.token_urlsafe(32)
        cache.set(
            _cache_key(state),
            {
                "mode": "link",
                "target_user_id": target.id,
                "linked_by_id": request.user.id if target != request.user else None,
            },
            timeout=600,  # 10 minutes
        )

        authorization_url, _ = GoogleAuthService.get_authorization_url(state=state)
        return Response({"authorization_url": authorization_url})


# ── OAuth initiation (unauthenticated — login) ──────────────────────────

class GoogleLoginView(APIView):
    """GET /api/auth/google/login/ — start OAuth for login."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not GoogleAuthService.is_configured():
            return Response(
                {"error": "Google OAuth is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        state = secrets.token_urlsafe(32)
        cache.set(_cache_key(state), {"mode": "login"}, timeout=600)

        authorization_url, _ = GoogleAuthService.get_authorization_url(state=state)
        return Response({"authorization_url": authorization_url})


# ── OAuth callback (AllowAny — Google redirects here) ────────────────────

class GoogleCallbackView(APIView):
    """GET /api/auth/google/callback/ — handles the Google redirect."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        # Base URL for frontend redirects
        base_url = "/"

        if error:
            return HttpResponseRedirect(f"{base_url}settings?google=error&detail={error}")

        if not code or not state:
            return HttpResponseRedirect(f"{base_url}settings?google=error&detail=missing_params")

        # Verify state
        state_data = cache.get(_cache_key(state))
        if not state_data:
            return HttpResponseRedirect(f"{base_url}settings?google=error&detail=invalid_state")
        cache.delete(_cache_key(state))

        # Exchange code for credentials
        try:
            google_id, email, credentials_json = GoogleAuthService.exchange_code(code)
        except Exception:
            return HttpResponseRedirect(f"{base_url}settings?google=error&detail=exchange_failed")

        mode = state_data.get("mode", "link")

        if mode == "link":
            return self._handle_link(state_data, google_id, email, credentials_json, base_url)
        else:
            return self._handle_login(google_id, email, credentials_json, base_url)

    def _handle_link(self, state_data, google_id, email, credentials_json, base_url):
        """Link Google account to an existing user."""
        from apps.projects.models import User

        target_user_id = state_data["target_user_id"]
        linked_by_id = state_data.get("linked_by_id")

        try:
            target_user = User.objects.get(pk=target_user_id)
        except User.DoesNotExist:
            return HttpResponseRedirect(f"{base_url}settings?google=error&detail=user_not_found")

        linked_by = None
        if linked_by_id:
            try:
                linked_by = User.objects.get(pk=linked_by_id)
            except User.DoesNotExist:
                pass

        # Check if this google_id is already linked to a different user
        existing = GoogleAccount.objects.filter(google_id=google_id).exclude(user=target_user).first()
        if existing:
            return HttpResponseRedirect(
                f"{base_url}settings?google=error&detail=already_linked_other"
            )

        GoogleAuthService.link_account(target_user, google_id, email, credentials_json, linked_by)
        return HttpResponseRedirect(f"{base_url}settings?google=linked")

    def _handle_login(self, google_id, email, credentials_json, base_url):
        """Log in via Google — find existing linked account."""
        try:
            account = GoogleAccount.objects.select_related("user").get(google_id=google_id)
        except GoogleAccount.DoesNotExist:
            return HttpResponseRedirect(
                f"{base_url}?google_error=no_account"
            )

        user = account.user
        if not user.is_active:
            return HttpResponseRedirect(f"{base_url}?google_error=inactive")

        # Update stored credentials (they may have been refreshed)
        account.encrypted_credentials = GoogleAuthService.encrypt_credentials(credentials_json)
        account.save(update_fields=["encrypted_credentials", "updated_at"])

        # Issue a DRF token
        token, _ = Token.objects.get_or_create(user=user)
        return HttpResponseRedirect(f"{base_url}?token={token.key}")


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
