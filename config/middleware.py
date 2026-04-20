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
    """Stamp ``Cache-Control: no-store`` on every ``/api/*`` response that
    didn't set its own ``Cache-Control`` header.

    Views can opt out by setting their own header (e.g.
    ``Cache-Control: public, max-age=60``) when the response is safely
    cacheable — public, non-user-scoped data only. The default protects
    against a CDN or browser serving a stale authenticated response to
    a different user. When opting out, the view author owns the decision
    that the response contains NO user-scoped data.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and "Cache-Control" not in response:
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
