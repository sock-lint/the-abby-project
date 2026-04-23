from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from config.viewsets import (
    RoleFilteredQuerySetMixin,
    child_not_found_response,
    get_child_or_404,
)

from .models import MovementSession, MovementType
from .serializers import (
    MovementSessionSerializer,
    MovementSessionWriteSerializer,
    MovementTypeSerializer,
)
from .services import MovementSessionError, MovementSessionService


class MovementTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only catalog of session activity kinds.

    Visible to both parents and children — the picker on the log modal
    needs to render these regardless of role. Authoring lives in
    ``seed_data`` + parent /manage CRUD (future).
    """

    serializer_class = MovementTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = MovementType.objects.filter(is_active=True).prefetch_related(
        "skill_tags__skill__category",
    )


class MovementSessionViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MovementSessionSerializer
    queryset = MovementSession.objects.select_related(
        "user", "movement_type",
    )
    role_filter_field = "user"
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def create(self, request, *args, **kwargs):
        write = MovementSessionWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)

        # Parent can log on behalf of a child via optional user_id.
        target_user = request.user
        if request.user.role == "parent":
            child_id = request.data.get("user_id")
            if child_id:
                target_user = get_child_or_404(child_id)
                if target_user is None:
                    return child_not_found_response()

        try:
            mt = MovementType.objects.get(
                pk=write.validated_data["movement_type_id"],
            )
        except MovementType.DoesNotExist:
            return Response(
                {"error": "movement_type_id not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = MovementSessionService.log_session(
                target_user,
                movement_type=mt,
                duration_minutes=write.validated_data["duration_minutes"],
                intensity=write.validated_data.get(
                    "intensity", MovementSession.Intensity.MEDIUM,
                ),
                notes=write.validated_data.get("notes", ""),
            )
        except MovementSessionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            MovementSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """Owner or parent. Counter is NOT decremented — anti-farm."""
        instance = self.get_object()
        if request.user.role != "parent" and instance.user_id != request.user.id:
            raise PermissionDenied("You can only delete your own sessions.")
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
