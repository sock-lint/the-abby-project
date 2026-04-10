from rest_framework import status
from rest_framework.response import Response


class RoleFilteredQuerySetMixin:
    """Filter queryset by user role: parents see all, children see their own.

    Subclasses set ``role_filter_field`` (default ``"user"``) to the lookup
    used when filtering for children, e.g. ``"assigned_to"`` or
    ``"project__assigned_to"``.
    """

    role_filter_field = "user"

    def get_role_filtered_queryset(self, queryset):
        user = self.request.user
        if user.role == "parent":
            return queryset
        return queryset.filter(**{self.role_filter_field: user})


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
