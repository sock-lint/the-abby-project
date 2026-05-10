import hashlib
import re

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
    # Ingestion urls must come BEFORE projects/ so /api/projects/ingest/
    # matches the ingest router first — otherwise `ingest` is interpreted as
    # a project pk by the projects viewset.
    # Accounts urls (signup) MUST come before projects/ so /api/auth/signup/
    # is matched as a literal path, not consumed by the AuthView's URL.
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.families.urls")),
    path("api/", include("apps.ingestion.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.timecards.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.achievements.urls")),
    path("api/", include("apps.portfolio.urls")),
    path("api/", include("apps.rewards.urls")),
    path("api/", include("apps.chores.urls")),
    path("api/", include("apps.homework.urls")),
    path("api/", include("apps.rpg.urls")),
    path("api/", include("apps.habits.urls")),
    path("api/", include("apps.pets.urls")),
    path("api/", include("apps.quests.urls")),
    path("api/", include("apps.google_integration.urls")),
    path("api/", include("apps.activity.urls")),
    path("api/", include("apps.chronicle.urls")),
    path("api/", include("apps.creations.urls")),
    path("api/", include("apps.lorebook.urls")),
    path("api/", include("apps.movement.urls")),
    path("api/", include("apps.wellbeing.urls")),
    # Dev-tools REST surface. URLs always mount — the gate runs at the
    # view permission layer (``IsDevToolsEnabled``) so it's re-checked
    # per request and survives runtime ``DEV_TOOLS_ENABLED`` toggles.
    # See ``apps/dev_tools/gate.py`` + ``apps/dev_tools/permissions.py``.
    path("api/dev/", include("apps.dev_tools.urls")),
]

# Serve /media/ through Django when uploads live on local disk. With
# USE_S3_STORAGE=true (production), uploads live in MinIO and the browser
# fetches them directly from s3.neato.digital via presigned URLs — Django
# never touches the bytes, so this route is dropped to avoid exposing an
# empty (or stale) media directory at a public path.
if not settings.USE_S3_STORAGE:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            static_serve,
            {"document_root": str(settings.MEDIA_ROOT)},
        ),
    ]

# PWA root files — these MUST be served from / (not /static/) so the service
# worker has root scope and the manifest serves with the right content type.
# Inserted before the SPA catch-all so it doesn't intercept them.
_PWA_ROOT_FILES = [
    "sw.js",
    "registerSW.js",
    "manifest.webmanifest",
    "pwa-192x192.png",
    "pwa-512x512.png",
    "maskable-icon-512x512.png",
    "apple-touch-icon.png",
    "favicon.svg",
]


def _pwa_static_serve(request, path):
    """Serve a PWA root file from frontend_dist with the right cache headers.
    sw.js MUST carry Cache-Control: no-cache so the browser revalidates on
    every page load — otherwise users get stuck on a stale SW that controls
    a bundle that no longer exists."""
    response = static_serve(
        request,
        path,
        document_root=str(settings.BASE_DIR / "frontend_dist"),
    )
    if path == "sw.js":
        response["Cache-Control"] = "no-cache"
    return response


urlpatterns += [
    re_path(
        rf"^(?P<path>{'|'.join(re.escape(f) for f in _PWA_ROOT_FILES)})$",
        _pwa_static_serve,
        name="pwa-root-file",
    ),
]

# SPA catch-all — MUST be last. React Router owns every other path.
# Exclude:
#   - static/ so missing assets get a proper 404 instead of index.html
#     served as text/html (WhiteNoise handles real static files at the
#     middleware layer before the URL resolver runs).
#   - .well-known/ so OAuth / MCP discovery probes (e.g. mcp-remote hitting
#     /.well-known/oauth-protected-resource on connect) get a proper 404
#     rather than index.html. HTML-when-JSON-expected crashes those clients
#     before they ever send the Authorization header. We don't implement
#     OAuth 2.1 PRD — a clean 404 is the right "not an OAuth server, use
#     your configured bearer token" signal.
urlpatterns += [
    re_path(r"^(?!static/|\.well-known/).*$", spa_view, name="spa"),
]
