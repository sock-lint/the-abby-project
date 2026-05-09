"""DRF permission for the parent-only ``/api/dev/*`` endpoints.

Same gate as the management commands: parent role + (DEBUG=True OR
DEV_TOOLS_ENABLED=True). The frontend reads the gate by hitting
``GET /api/dev/ping/`` — a 200 means the Test tab can render, anything
else means hide it.
"""
from __future__ import annotations

from rest_framework import permissions

from apps.dev_tools.gate import is_enabled


class IsDevToolsEnabled(permissions.BasePermission):
    message = "Dev tools are disabled in this environment."

    def has_permission(self, request, view):
        if not is_enabled():
            return False
        user = request.user
        return (
            user.is_authenticated
            and getattr(user, "role", None) == "parent"
        )
