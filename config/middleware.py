from django.db import connection
from django.http import JsonResponse


class HealthCheckMiddleware:
    """Intercept /health before Django's host validation runs.

    Placed first in MIDDLEWARE so that Docker / Coolify health probes
    (which hit ``http://localhost:8000/health``) succeed even when
    ALLOWED_HOSTS only contains the public FQDN.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health":
            try:
                connection.ensure_connection()
            except Exception:
                return JsonResponse(
                    {"status": "degraded", "db": "down"},
                    status=503,
                )
            return JsonResponse({"status": "ok", "db": "up"})
        return self.get_response(request)


class NoCacheAPIMiddleware:
    """Stamp ``Cache-Control: no-store`` on every ``/api/*`` response.

    Why: without an explicit ``Cache-Control`` header, browsers apply RFC 7234
    heuristic freshness to any 200 OK body. If an upstream proxy (Coolify /
    Traefik) ever returns a 200 with an HTML "app is down" page for an API
    URL — which has happened in production — the browser will happily serve
    that stale HTML from disk cache for hours afterward, and the SPA's
    ``res.json()`` call blows up on ``<!DOCTYPE html>``. ``no-store`` on every
    API response prevents that trap regardless of what upstream does.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        return response


class SentryUserMiddleware:
    """Set Sentry user context from the authenticated Django user.

    Placed after AuthenticationMiddleware so ``request.user`` is available
    for session-authenticated requests (e.g. admin).  For DRF
    TokenAuthentication the SDK captures the user automatically at
    request-end via ``send_default_pii=True``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            import sentry_sdk
        except ImportError:
            return self.get_response(request)

        if hasattr(request, "user") and request.user.is_authenticated:
            sentry_sdk.set_user(
                {
                    "id": request.user.id,
                    "username": request.user.username,
                    "role": getattr(request.user, "role", "unknown"),
                }
            )
        else:
            sentry_sdk.set_user(None)

        return self.get_response(request)
