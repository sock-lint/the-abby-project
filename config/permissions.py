"""Shared DRF permission classes."""
from rest_framework import permissions


def _resolve_object_family_id(obj):
    """Best-effort resolution of an object's family scope.

    Returns the family id when we can find one via known attribute paths,
    or None when we can't (in which case the queryset-level filter is the
    authority — object-level returns True so we don't double-block).
    """
    family_id = getattr(obj, "family_id", None)
    if family_id is not None:
        return family_id
    for attr in ("user", "assigned_to", "created_by", "child", "parent"):
        related = getattr(obj, attr, None)
        if related is not None:
            family_id = getattr(related, "family_id", None)
            if family_id is not None:
                return family_id
    return None


class IsParent(permissions.BasePermission):
    """Allows access only to authenticated users with ``role == 'parent'``.

    Object-level: if the object resolves to a family different from the
    caller's, deny — defense in depth on top of queryset filtering.
    """

    message = "Parents only."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, "role", None) == "parent"
        )

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "role", None) != "parent":
            return False
        caller_family_id = getattr(request.user, "family_id", None)
        if caller_family_id is None:
            return False
        target_family_id = _resolve_object_family_id(obj)
        if target_family_id is None:
            # Couldn't resolve — defer to queryset-level scoping.
            return True
        return target_family_id == caller_family_id


class IsStaffParent(permissions.BasePermission):
    """Allows access only to staff parents (for global content authoring).

    Skill / Badge / Lorebook write actions gate on this so a regular
    parent (created via signup) can't pollute global content visible
    to other families. The founding superuser stays ``is_staff=True``.
    """

    message = "Staff parents only."

    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated
            and getattr(user, "role", None) == "parent"
            and user.is_staff
        )
