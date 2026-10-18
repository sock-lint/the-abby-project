"""Production error responses for paths outside registered endpoints."""

from django.http import JsonResponse
from django.views.defaults import page_not_found as default_page_not_found


def page_not_found(request, exception):
    if request.path_info == "/api" or request.path_info.startswith("/api/"):
        response = JsonResponse({"detail": "Not found."}, status=404)
        response["Cache-Control"] = "no-store"
        return response
    return default_page_not_found(request, exception)
