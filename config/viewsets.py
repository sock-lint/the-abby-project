from rest_framework import permissions, status
from rest_framework.response import Response

from config.permissions import IsParent


def filter_queryset_by_role(user, queryset, role_filter_field="user"):
    """Filter a queryset by user role: parents see all, children see own.

    Usable from viewsets (via :class:`RoleFilteredQuerySetMixin`) and from
    APIViews that need to apply the same rule to multiple querysets with
    different filter fields.
    """
    if user.role == "parent":
        return queryset
    return queryset.filter(**{role_filter_field: user})


class RoleFilteredQuerySetMixin:
    """Filter queryset by user role: parents see all, children see their own.

    Subclasses set ``role_filter_field`` (default ``"user"``) to the lookup
    used when filtering for children, e.g. ``"assigned_to"`` or
    ``"project__assigned_to"``.
    """

    role_filter_field = "user"

    def get_role_filtered_queryset(self, queryset):
        return filter_queryset_by_role(
            self.request.user, queryset, self.role_filter_field,
        )


class NestedProjectResourceMixin:
    """Shared get_queryset/perform_create for resources nested under a project.

    Expects the URL conf to capture ``project_pk``.
    """

    def get_queryset(self):
        return super().get_queryset().filter(
            project_id=self.kwargs.get("project_pk"),
        )

    def perform_create(self, serializer):
        serializer.save(project_id=self.kwargs["project_pk"])


def get_child_or_404(child_id):
    """Look up a child user by ID, returning None if not found."""
    from apps.projects.models import User

    try:
        return User.objects.get(id=child_id, role="child")
    except User.DoesNotExist:
        return None


def child_not_found_response():
    return Response(
        {"error": "Child not found"},
        status=status.HTTP_404_NOT_FOUND,
    )


class ParentWritePermissionMixin:
    """Return IsParent for write actions, IsAuthenticated for read actions."""

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]


class WriteReadSerializerMixin:
    """Switch serializer class based on action.

    Set ``write_serializer_class`` on the viewset; the default
    ``serializer_class`` is used for read actions.
    """

    write_serializer_class = None

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return self.write_serializer_class
        return self.serializer_class


def resolve_target_user(request, source="query_params"):
    """Resolve a target child user from the request.

    For parents, looks up ``user_id`` from *source* (``"query_params"``
    or ``"data"``).  Children are always the target themselves.

    Returns ``(user, None)`` on success or ``(None, Response)`` on error.
    """
    user = request.user
    target_user = user
    if user.role == "parent":
        bucket = request.query_params if source == "query_params" else request.data
        child_id = bucket.get("user_id")
        if child_id:
            target_user = get_child_or_404(child_id)
            if target_user is None:
                return None, child_not_found_response()
    return target_user, None
