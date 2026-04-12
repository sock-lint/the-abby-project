from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin

from .models import Chore, ChoreCompletion
from .serializers import (
    ChoreCompletionSerializer, ChoreSerializer, ChoreWriteSerializer,
)
from .services import ChoreNotAvailableError, ChoreService


class ChoreViewSet(viewsets.ModelViewSet):
    serializer_class = ChoreSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return Chore.objects.all()
        return Chore.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ChoreWriteSerializer
        return ChoreSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        user = request.user
        if user.role == "child":
            chores = ChoreService.get_available_chores(user)
            data = []
            for chore in chores:
                serialized = ChoreSerializer(chore).data
                serialized["is_available"] = not chore.is_done_today
                serialized["today_status"] = chore.today_completion_status
                serialized["today_completion_id"] = chore.today_completion_id
                data.append(serialized)
            return Response(data)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        chore = self.get_object()
        try:
            completion = ChoreService.submit_completion(
                request.user, chore, notes=request.data.get("notes", ""),
            )
        except ChoreNotAvailableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ChoreCompletionSerializer(completion).data,
            status=status.HTTP_201_CREATED,
        )


class ChoreCompletionViewSet(RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ChoreCompletionSerializer
    queryset = ChoreCompletion.objects.select_related("chore", "user")

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(super().get_queryset())
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        completion = self.get_object()
        ChoreService.approve_completion(completion, request.user)
        return Response(ChoreCompletionSerializer(completion).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def reject(self, request, pk=None):
        completion = self.get_object()
        ChoreService.reject_completion(completion, request.user)
        return Response(ChoreCompletionSerializer(completion).data)
