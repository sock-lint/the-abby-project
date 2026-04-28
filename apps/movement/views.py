from django.db.models import ProtectedError
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
    MovementTypeWriteSerializer,
)
from .services import (
    MovementSessionError,
    MovementSessionService,
    MovementTypeError,
    MovementTypeService,
)


class MovementTypeViewSet(viewsets.ModelViewSet):
    """Catalog of session activity kinds — readable by everyone, writable by any user.

    GET is visible to both parents and children — the picker on the log
    modal needs to render these regardless of role. POST lets a child (or
    parent) add a new activity kind on the fly; child-created types become
    globally available, matching the self-reported doctrine that governs
    ``MovementSession``. DELETE is restricted to the creator (or a parent)
    and blocks when any session already references the type.

    No PATCH/PUT — types are write-once for now. If a name needs fixing,
    delete and re-create before anyone has logged against it.
    """

    serializer_class = MovementTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = MovementType.objects.filter(is_active=True).prefetch_related(
        "skill_tags__skill__category",
    )
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        write = MovementTypeWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)

        try:
            movement_type = MovementTypeService.create_type(
                request.user,
                name=write.validated_data["name"],
                icon=write.validated_data.get("icon", ""),
                default_intensity=write.validated_data.get(
                    "default_intensity", MovementType.Intensity.MEDIUM,
                ),
                primary_skill_id=write.validated_data["primary_skill_id"],
                secondary_skill_id=write.validated_data.get("secondary_skill_id"),
            )
        except MovementTypeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Re-fetch with prefetches so the response carries skill_tags.
        movement_type = (
            MovementType.objects.prefetch_related("skill_tags__skill__category")
            .get(pk=movement_type.pk)
        )
        return Response(
            MovementTypeSerializer(movement_type).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """Creator or parent can delete; any existing session blocks it."""
        instance = self.get_object()
        is_parent = request.user.role == "parent"
        is_creator = (
            instance.created_by_id is not None
            and instance.created_by_id == request.user.id
        )
        if not (is_parent or is_creator):
            raise PermissionDenied(
                "You can only delete activities you created.",
            )

        try:
            instance.delete()
        except ProtectedError:
            session_count = MovementSession.objects.filter(
                movement_type=instance,
            ).count()
            return Response(
                {"error": f"Already used in {session_count} session(s)."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                target_user = get_child_or_404(child_id, requesting_user=request.user)
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
