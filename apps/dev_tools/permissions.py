"""DRF permission for the parent-only ``/api/dev/*`` endpoints.

Gate: ``parent role + is_staff=True + (DEBUG=True OR DEV_TOOLS_ENABLED=True)``.

The ``is_staff`` requirement is what makes "production access for the
deployment owner only" possible without unlocking the panel for every
parent in a multi-family deployment. ``createsuperuser`` sets
``is_staff=True`` automatically; signup-created parents do NOT, so a
parent who registered through ``/api/auth/signup/`` stays locked out
even if ``DEV_TOOLS_ENABLED=True`` ships in the env.

The frontend reads the gate by hitting ``GET /api/dev/ping/`` — a 200
means the Test tab can render, anything else means hide it.
"""
from __future__ import annotations

from rest_framework import permissions

from apps.dev_tools.gate import is_enabled


class IsDevToolsEnabled(permissions.BasePermission):
    message = (
        "Dev tools require an authenticated staff parent and "
        "DEBUG=True or DEV_TOOLS_ENABLED=True."
    )

    def has_permission(self, request, view):
        if not is_enabled():
            return False
        user = request.user
        return (
            user.is_authenticated
            and getattr(user, "role", None) == "parent"
            and user.is_staff
        )
