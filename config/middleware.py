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
