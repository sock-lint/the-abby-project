from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import WriteReadSerializerMixin

from .models import CharacterProfile, Habit, HabitLog
from .serializers import (
    CharacterProfileSerializer,
    HabitLogSerializer,
    HabitSerializer,
    HabitWriteSerializer,
)
from .services import GameLoopService, HabitService


class CharacterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _created = CharacterProfile.objects.get_or_create(user=request.user)
        serializer = CharacterProfileSerializer(profile)
        return Response(serializer.data)


class StreakView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _created = CharacterProfile.objects.get_or_create(user=request.user)
        return Response(
            {
                "login_streak": profile.login_streak,
                "longest_login_streak": profile.longest_login_streak,
                "last_active_date": profile.last_active_date,
                "perfect_days_count": profile.perfect_days_count,
            }
        )


class HabitViewSet(WriteReadSerializerMixin, viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    write_serializer_class = HabitWriteSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Habit.objects.all()
        if user.role == "child":
            qs = qs.filter(user=user)
        return qs

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "child":
            serializer.save(user=user, created_by=user)
        else:
            serializer.save(created_by=user)

    @action(detail=True, methods=["post"])
    def log(self, request, pk=None):
        habit = self.get_object()
        direction = request.data.get("direction")
        try:
            direction = int(direction)
        except (TypeError, ValueError):
            return Response(
                {"error": "direction must be an integer (+1 or -1)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = HabitService.log_tap(request.user, habit, direction)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        game_event = None
        if direction == 1:
            game_event = GameLoopService.on_task_completed(
                request.user, "habit_log", {"habit_id": habit.pk},
            )

        return Response({**result, "game_event": game_event})
