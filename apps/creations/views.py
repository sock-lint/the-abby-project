from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from config.permissions import IsParent
from config.viewsets import (
    RoleFilteredQuerySetMixin,
    child_not_found_response,
    get_child_or_404,
)

from .models import Creation
from .serializers import (
    CreationApproveSerializer,
    CreationSerializer,
    CreationWriteSerializer,
)
from .services import CreationError, CreationService


class CreationViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = CreationSerializer
    queryset = (
        Creation.objects.select_related(
            "user", "primary_skill", "primary_skill__category",
            "secondary_skill", "secondary_skill__category", "decided_by",
            "chronicle_entry",
        )
        .prefetch_related("bonus_skill_tags__skill__category")
    )
    role_filter_field = "user"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def create(self, request, *args, **kwargs):
        write = CreationWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)

        # Parent can create on behalf of a child via optional user_id.
        target_user = request.user
        if request.user.role == "parent":
            child_id = request.data.get("user_id")
            if child_id:
                target_user = get_child_or_404(child_id)
                if target_user is None:
                    return child_not_found_response()

        try:
            creation = CreationService.log_creation(
                target_user,
                image=write.validated_data["image"],
                audio=write.validated_data.get("audio"),
                caption=write.validated_data.get("caption", ""),
                primary_skill_id=write.validated_data["primary_skill_id"],
                secondary_skill_id=write.validated_data.get("secondary_skill_id"),
            )
        except CreationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            CreationSerializer(creation).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """Blob-first delete. Mirrors HomeworkProofViewSet.destroy."""
        instance = self.get_object()
        if request.user.role != "parent" and instance.user_id != request.user.id:
            raise PermissionDenied("You can only delete your own creations.")
        if instance.image:
            instance.image.delete(save=False)
        if instance.audio:
            instance.audio.delete(save=False)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def submit(self, request, pk=None):
        """Owner or parent submits for bonus review."""
        creation = self.get_object()
        if request.user.role != "parent" and creation.user_id != request.user.id:
            raise PermissionDenied("You can only submit your own creations.")
        CreationService.submit_for_bonus(creation)
        return Response(CreationSerializer(creation).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        creation = self.get_object()
        write = CreationApproveSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        try:
            CreationService.approve_bonus(
                creation,
                request.user,
                bonus_xp=write.validated_data.get(
                    "bonus_xp", CreationService.DEFAULT_BONUS_XP,
                ),
                extra_skill_tags=write.validated_data.get("skill_tags") or None,
                notes=write.validated_data.get("notes", ""),
            )
        except CreationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CreationSerializer(creation).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def reject(self, request, pk=None):
        creation = self.get_object()
        CreationService.reject_bonus(
            creation, request.user, notes=request.data.get("notes", ""),
        )
        return Response(CreationSerializer(creation).data)

    @action(detail=False, methods=["get"], permission_classes=[IsParent])
    def pending(self, request):
        """Parent-only queue of submitted Creations awaiting approval.

        Returned as a flat list shaped for ``useParentDashboard`` consumption.
        """
        pending = Creation.objects.filter(
            status=Creation.Status.PENDING,
        ).select_related(
            "user", "primary_skill", "primary_skill__category",
        ).order_by("-updated_at")
        return Response(CreationSerializer(pending, many=True).data)
