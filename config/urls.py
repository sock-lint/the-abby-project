import hashlib

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

# Load the built SPA entry point once at import time. In production the
# Docker build copies frontend/dist into BASE_DIR/frontend_dist. In local
# dev (python manage.py runserver) the file won't exist — React is served
# by `npm run dev` on :3000, which proxies /api here. We fall back to a
# short hint page so runserver doesn't crash.
_index_path = settings.BASE_DIR / "frontend_dist" / "index.html"
try:
    _INDEX_HTML = _index_path.read_text(encoding="utf-8")
except FileNotFoundError:
    _INDEX_HTML = (
        "<!doctype html><meta charset='utf-8'><title>Abby (dev)</title>"
        "<p>React bundle not built. Run <code>cd frontend &amp;&amp; npm run dev</code> "
        "and visit <a href='http://localhost:3000'>http://localhost:3000</a>.</p>"
    )

# Content-based ETag computed once at import time. Changes automatically on
# each redeployment (new Vite build → new asset hashes in the HTML → new ETag).
_INDEX_HTML_ETAG = hashlib.md5(_INDEX_HTML.encode()).hexdigest()


def spa_view(request):
    """Serve the built React index.html for any non-API, non-admin route."""
    # Return 304 if the browser already has the current version.
    if request.META.get("HTTP_IF_NONE_MATCH") == _INDEX_HTML_ETAG:
        return HttpResponse(status=304)
    response = HttpResponse(_INDEX_HTML, content_type="text/html; charset=utf-8")
    # Force revalidation so browsers never serve a stale index.html whose
    # hashed asset references (CSS/JS) no longer exist after a redeploy.
    response["Cache-Control"] = "no-cache"
    response["ETag"] = _INDEX_HTML_ETAG
    return response


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.timecards.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.achievements.urls")),
    path("api/", include("apps.portfolio.urls")),
    path("api/", include("apps.rewards.urls")),
]

# Serve /media/ through Django in all environments. Fine at home-app scale;
# swap for a proper object store if this ever outgrows a single server.
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        static_serve,
        {"document_root": str(settings.MEDIA_ROOT)},
    ),
]

# SPA catch-all — MUST be last. React Router owns every other path.
# Exclude static/ so missing assets get a proper 404 instead of index.html
# served as text/html (WhiteNoise handles real static files at the middleware
# layer before the URL resolver runs).
urlpatterns += [re_path(r"^(?!static/).*$", spa_view, name="spa")]
