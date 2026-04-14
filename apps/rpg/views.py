from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import WriteReadSerializerMixin

from .models import CharacterProfile, Habit, HabitLog, UserInventory, DropLog
from .serializers import (
    CharacterProfileSerializer,
    HabitLogSerializer,
    HabitSerializer,
    HabitWriteSerializer,
    UserInventorySerializer,
    DropLogSerializer,
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


class InventoryView(APIView):
    """GET /api/inventory/ — current user's item inventory grouped by type."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entries = UserInventory.objects.filter(
            user=request.user,
        ).select_related("item").order_by("item__item_type", "item__name")
        return Response(UserInventorySerializer(entries, many=True).data)


class RecentDropsView(APIView):
    """GET /api/drops/recent/ — last 10 drops for the user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        drops = DropLog.objects.filter(
            user=request.user,
        ).select_related("item")[:10]
        return Response(DropLogSerializer(drops, many=True).data)


class CosmeticsView(APIView):
    """GET /api/cosmetics/ — owned cosmetics grouped by slot."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .serializers import ItemDefinitionSerializer
        from .services import CosmeticService

        owned = CosmeticService.list_owned_cosmetics(request.user)
        return Response({
            slot: ItemDefinitionSerializer(items, many=True).data
            for slot, items in owned.items()
        })


class EquipCosmeticView(APIView):
    """POST /api/character/equip/ — equip a cosmetic item."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services import CosmeticService

        item_id = request.data.get("item_id")
        if not item_id:
            return Response({"error": "item_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = CosmeticService.equip(request.user, item_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class UnequipCosmeticView(APIView):
    """POST /api/character/unequip/ — clear a cosmetic slot."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services import CosmeticService

        slot = request.data.get("slot")
        if not slot:
            return Response({"error": "slot is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = CosmeticService.unequip(request.user, slot)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
