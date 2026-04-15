from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent

from .models import CharacterProfile, ItemDefinition, UserInventory, DropLog
from .serializers import (
    CharacterProfileSerializer,
    ItemDefinitionSerializer,
    UserInventorySerializer,
    DropLogSerializer,
)


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


class ItemCatalogView(ListAPIView):
    """GET /api/items/catalog/ — parent-only browse of every authored ItemDefinition."""
    permission_classes = [permissions.IsAuthenticated, IsParent]
    serializer_class = ItemDefinitionSerializer
    pagination_class = None

    def get_queryset(self):
        return ItemDefinition.objects.select_related(
            "pet_species", "potion_type", "food_species",
        ).order_by("item_type", "rarity", "name")


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
