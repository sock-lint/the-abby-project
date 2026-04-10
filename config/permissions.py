"""Shared DRF permission classes."""
from rest_framework import permissions


class IsParent(permissions.BasePermission):
    """Allows access only to authenticated users with ``role == 'parent'``."""

    message = "Parents only."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, "role", None) == "parent"
        )
