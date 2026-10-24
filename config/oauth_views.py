"""HTTP views that round out django-oauth-toolkit for the MCP-spec flow.

Five surfaces live here:

1. ``WellKnownProtectedResourceView``     RFC 9728 — resource metadata
2. ``WellKnownAuthorizationServerView``   RFC 8414 — auth-server metadata
3. ``AbbyAuthorizationView``              DOT AuthorizationView + staff-parent gate
4. ``DynamicClientRegistrationView``      RFC 7591 — dynamic client registration
5. ``OAuthLoginView``                     tiny username/password loop-back form

Everything else (token exchange, refresh, revoke, introspect) comes from
``oauth2_provider.urls``.
"""
from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
from django.views.decorators.cache import cache_control
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken
from oauth2_provider.views import AuthorizationView
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView


# ---------------------------------------------------------------------------
# Discovery (RFC 9728 + RFC 8414)
# ---------------------------------------------------------------------------


def _origin(request) -> str:
    """Return the public origin for absolute URLs in discovery responses.

    Prefer ``settings.SITE_URL`` (env-driven, set in production), fall back
    to the request's scheme+host (works in dev / tests where SITE_URL is
    the localhost default).
    """
    site = getattr(settings, "SITE_URL", "") or ""
    if site:
        return site.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


@method_decorator(cache_control(public=True, max_age=3600), name="get")
class WellKnownProtectedResourceView(View):
    """RFC 9728 — Protected Resource Metadata.

    Tells MCP clients ("the resource you're trying to talk to is protected
    by this auth server"). Returns the canonical resource identifier plus
    the URL of the auth server (this same Django app), the bearer methods
    we accept, and the scope that grants access.

    Cached for an hour — the response only changes when SITE_URL or the
    deployment topology changes.
    """

    def get(self, request, *args, **kwargs):
        origin = _origin(request)
        resource = getattr(settings, "MCP_RESOURCE_URL", f"{origin}/mcp")
        body = {
            "resource": resource,
            "authorization_servers": [origin],
            "bearer_methods_supported": ["header"],
            "scopes_supported": list(
                (getattr(settings, "OAUTH2_PROVIDER", {}) or {}).get("SCOPES", {}).keys()
            ),
            "resource_documentation": f"{origin}/manage",
        }
        return JsonResponse(body)


@method_decorator(cache_control(public=True, max_age=3600), name="get")
class WellKnownAuthorizationServerView(View):
    """RFC 8414 — OAuth 2.0 Authorization Server Metadata.

    Hand-rolled (rather than DOT's OIDC-flavored built-in) so the JSON
    shape matches MCP-spec expectations exactly: code grant + refresh
    token, S256 PKCE only, public-client auth method only, dynamic client
    registration endpoint advertised.
    """

    def get(self, request, *args, **kwargs):
        origin = _origin(request)
        body = {
            "issuer": origin,
            "authorization_endpoint": f"{origin}/oauth/authorize/",
            "token_endpoint": f"{origin}/oauth/token/",
            "registration_endpoint": f"{origin}/oauth/register/",
            "revocation_endpoint": f"{origin}/oauth/revoke_token/",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": list(
                (getattr(settings, "OAUTH2_PROVIDER", {}) or {}).get("SCOPES", {}).keys()
            ),
            "service_documentation": f"{origin}/manage",
        }
        return JsonResponse(body)


# ---------------------------------------------------------------------------
# Authorization view — staff-parent-only gate on top of DOT's
# ---------------------------------------------------------------------------


def _is_staff_parent(user) -> bool:
    """The single predicate that gates OAuth grants. Mirrors IsStaffParent."""
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and getattr(user, "role", None) == "parent"
        and user.is_staff
    )


class AbbyAuthorizationView(AuthorizationView):
    """Staff-parent consent with one exact, durable RFC 8707 resource binding."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not _is_staff_parent(request.user):
            return render(
                request,
                "oauth2_provider/forbidden.html",
                {"reason": "Your account isn't authorized to grant MCP access."},
                status=403,
            )
        if request.user.is_authenticated:
            params = request.POST if request.method == "POST" else request.GET
            if params.getlist("resource") != [settings.MCP_RESOURCE_URL]:
                return JsonResponse({
                    "error": "invalid_target",
                    "error_description": "Specify exactly the advertised MCP resource.",
                }, status=400)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mcp_resource"] = settings.MCP_RESOURCE_URL
        return context

    def create_authorization_response(self, request, scopes, credentials, allow):
        # DOT versions before native RFC 8707 support drop extra form fields.
        # Bind from the validated consent request, never an untrusted token override.
        credentials = {**credentials, "resource": [settings.MCP_RESOURCE_URL]}
        return super().create_authorization_response(request, scopes, credentials, allow)


# ---------------------------------------------------------------------------
# Login-during-consent — tiny username/password loop
# ---------------------------------------------------------------------------


def _safe_next_url(value: str) -> str | None:
    """Reject open-redirects: only same-origin paths starting with ``/oauth/`` allowed."""
    if not value or not value.startswith("/"):
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path.startswith("/oauth/"):
        return None
    return value


class OAuthLoginThrottle(SimpleRateThrottle):
    scope = "oauth_login"

    def get_cache_key(self, request, view):
        # Forwarded headers are client-controlled unless a separately trusted
        # proxy contract validates them. Bound attempts by the transport peer;
        # clients behind the same proxy intentionally share this conservative cap.
        peer = request.META.get("REMOTE_ADDR") or "unknown-peer"
        return self.cache_format % {"scope": self.scope, "ident": peer}


class OAuthLoginView(View):
    """Minimal username/password form used when /oauth/authorize/ needs auth.

    Django's ``LoginRequiredMixin`` (inherited by AuthorizationView) bounces
    unauthenticated users to ``settings.LOGIN_URL`` (=``/oauth/login/``).
    This view authenticates them and redirects back via ``?next=``. Only
    same-origin ``/oauth/...`` next-URLs are honored.
    """

    template_name = "oauth2_provider/login.html"

    def get(self, request, *args, **kwargs):
        next_url = _safe_next_url(request.GET.get("next", "")) or "/manage"
        return render(request, self.template_name, {"next": next_url, "error": None})

    def post(self, request, *args, **kwargs):
        throttle = OAuthLoginThrottle()
        if not throttle.allow_request(request, self):
            import math
            response = render(request, self.template_name, {
                "next": _safe_next_url(request.POST.get("next", "")) or "/manage",
                "error": "Too many sign-in attempts. Try again shortly.",
            }, status=429)
            response["Retry-After"] = str(math.ceil(throttle.wait() or 60))
            return response
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        next_url = _safe_next_url(request.POST.get("next", "")) or "/manage"
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return render(
                request,
                self.template_name,
                {"next": next_url, "error": "Invalid username or password."},
                status=401,
            )
        if not _is_staff_parent(user):
            return render(
                request,
                self.template_name,
                {
                    "next": next_url,
                    "error": "This account isn't authorized to grant MCP access.",
                },
                status=403,
            )
        login(request, user)
        return HttpResponseRedirect(next_url)


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------


class DynamicClientRegistrationView(APIView):
    """RFC 7591 — public dynamic registration of OAuth clients.

    POST a JSON body with ``client_name`` + ``redirect_uris``; receive a
    fresh ``client_id`` for a public, PKCE-only auth-code client. No
    secrets issued — public clients use PKCE in lieu of a secret.

    Throttled per IP to keep drive-by spam from filling the Application
    table. The throttle is the only guardrail; this endpoint is
    intentionally unauthenticated (the spec calls for it).
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []   # no DRF auth — JSON body, no cookies
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "oauth_register"

    def post(self, request, *args, **kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        client_name = (body.get("client_name") or "").strip() or "MCP client"

        redirect_uris = body.get("redirect_uris") or []
        if isinstance(redirect_uris, str):
            redirect_uris = [redirect_uris]
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return Response(
                {"error": "invalid_redirect_uri", "error_description": "redirect_uris must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cleaned: list[str] = []
        for uri in redirect_uris:
            if not isinstance(uri, str) or not uri.strip():
                return Response(
                    {"error": "invalid_redirect_uri", "error_description": "all redirect_uris must be non-empty strings"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            parsed = urlparse(uri)
            if parsed.scheme not in {"http", "https"}:
                return Response(
                    {"error": "invalid_redirect_uri", "error_description": f"unsupported scheme: {parsed.scheme}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cleaned.append(uri.strip())

        # Force public + auth-code + PKCE-only regardless of what the client asks.
        application = Application.objects.create(
            name=client_name[:255],
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=" ".join(cleaned),
            client_secret="",   # public clients carry no secret
            skip_authorization=False,
        )

        body_out = {
            "client_id": application.client_id,
            "client_id_issued_at": int(application.created.timestamp()),
            "client_name": application.name,
            "redirect_uris": cleaned,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        return Response(body_out, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Admin REST surface — list/revoke connections and remove unused registrations
# ---------------------------------------------------------------------------


def _applications_with_cleanup_eligibility():
    """Protect live credentials for every user, including pending consent."""
    now = timezone.now()
    return Application.objects.annotate(
        can_delete=(
            ~Exists(AccessToken.objects.filter(application_id=OuterRef("pk"), expires__gt=now))
            & ~Exists(RefreshToken.objects.filter(application_id=OuterRef("pk"), revoked__isnull=True))
            & ~Exists(Grant.objects.filter(application_id=OuterRef("pk"), expires__gt=now))
        ),
    )


class AdminApplicationListView(APIView):
    """Staff-parent-only list of registered OAuth Applications."""

    def get(self, request):
        if not _is_staff_parent(request.user):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        rows = _applications_with_cleanup_eligibility().order_by("-created").values(
            "client_id", "name", "client_type", "redirect_uris", "created", "can_delete",
        )
        return Response({"applications": list(rows)})


class AdminApplicationDeleteView(APIView):
    """Remove a registration only while it has no live OAuth connection."""

    def delete(self, request, client_id: str):
        if not _is_staff_parent(request.user):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            try:
                app = Application.objects.select_for_update().get(client_id=client_id)
            except Application.DoesNotExist:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            # Use a new query after acquiring the lock so concurrent authorization
            # that finished while we waited is included in the eligibility check.
            can_delete = _applications_with_cleanup_eligibility().filter(pk=app.pk).values_list(
                "can_delete", flat=True,
            ).get()
            if not can_delete:
                return Response({
                    "code": "application_in_use",
                    "detail": "This client has active access, a refresh token, or a sign-in in progress. "
                              "Revoke its tokens or finish sign-in before removing the registration.",
                }, status=status.HTTP_409_CONFLICT)
            app.delete()
        return Response({"ok": True})


class AdminApplicationRevokeTokensView(APIView):
    """Staff-parent-only — revoke every active token for a given application."""

    def delete(self, request, client_id: str):
        if not _is_staff_parent(request.user):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        from django.utils import timezone
        from oauth2_provider.models import AccessToken, RefreshToken
        try:
            app = Application.objects.get(client_id=client_id)
        except Application.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # Expire access tokens; revoke refresh tokens (DOT's RefreshToken has a
        # revoked timestamp; AccessToken has expires).
        now = timezone.now()
        AccessToken.objects.filter(application=app, expires__gt=now).update(expires=now)
        for rt in RefreshToken.objects.filter(application=app, revoked__isnull=True):
            rt.revoke()
        return Response({"ok": True})


class AdminTokenListView(APIView):
    """List the caller's own active access tokens."""

    def get(self, request):
        if not _is_staff_parent(request.user):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        from django.utils import timezone
        from oauth2_provider.models import AccessToken
        now = timezone.now()
        rows = (
            AccessToken.objects
            .select_related("application")
            .filter(user=request.user, expires__gt=now)
            .order_by("-created")
        )
        return Response({
            "tokens": [
                {
                    "id": t.id,
                    "application_name": t.application.name if t.application else None,
                    "application_client_id": t.application.client_id if t.application else None,
                    "scope": t.scope,
                    "issued_at": t.created.isoformat() if t.created else None,
                    "expires_at": t.expires.isoformat() if t.expires else None,
                }
                for t in rows
            ]
        })


class AdminTokenRevokeView(APIView):
    """Revoke a single AccessToken row owned by the caller."""

    def delete(self, request, token_id: int):
        if not _is_staff_parent(request.user):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        from django.utils import timezone
        from oauth2_provider.models import AccessToken
        try:
            t = AccessToken.objects.get(id=token_id, user=request.user)
        except AccessToken.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        t.expires = timezone.now()
        t.save(update_fields=["expires"])
        # Best-effort: also revoke the paired refresh token if any.
        rt = getattr(t, "refresh_token", None)
        if rt is not None and rt.revoked is None:
            rt.revoke()
        return Response({"ok": True})
