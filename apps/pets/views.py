from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent

from .models import PetSpecies, UserPet, UserMount
from .serializers import (
    PetSpeciesCatalogSerializer,
    UserMountSerializer,
    UserPetSerializer,
)
from .services import PetService


class StableView(APIView):
    """GET /api/pets/stable/ — full pet/mount collection."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stable = PetService.get_stable(request.user)
        return Response({
            "pets": UserPetSerializer(stable["pets"], many=True).data,
            "mounts": UserMountSerializer(stable["mounts"], many=True).data,
            "total_pets": stable["total_pets"],
            "total_mounts": stable["total_mounts"],
            "total_possible": stable["total_possible"],
        })


class HatchPetView(APIView):
    """POST /api/pets/hatch/ — hatch egg + potion into a new pet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        egg_id = request.data.get("egg_item_id")
        potion_id = request.data.get("potion_item_id")
        if not egg_id or not potion_id:
            return Response(
                {"error": "egg_item_id and potion_item_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            pet = PetService.hatch_pet(request.user, egg_id, potion_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserPetSerializer(pet).data, status=status.HTTP_201_CREATED)


class FeedPetView(APIView):
    """POST /api/pets/{id}/feed/ — feed food to a pet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        food_id = request.data.get("food_item_id")
        if not food_id:
            return Response(
                {"error": "food_item_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = PetService.feed_pet(request.user, pk, food_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class ActivatePetView(APIView):
    """POST /api/pets/{id}/activate/ — set as active pet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            pet = PetService.set_active_pet(request.user, pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserPetSerializer(pet).data)


class MountsView(APIView):
    """GET /api/mounts/ — user's mount collection."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        mounts = UserMount.objects.filter(
            user=request.user,
        ).select_related("species", "potion")
        return Response(UserMountSerializer(mounts, many=True).data)


class PetSpeciesCatalogView(ListAPIView):
    """GET /api/pets/species/catalog/ — parent-only browse of every authored PetSpecies."""
    permission_classes = [permissions.IsAuthenticated, IsParent]
    serializer_class = PetSpeciesCatalogSerializer
    pagination_class = None

    def get_queryset(self):
        return PetSpecies.objects.prefetch_related("available_potions").order_by("name")


class ActivateMountView(APIView):
    """POST /api/mounts/{id}/activate/ — set as active mount."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            mount = PetService.set_active_mount(request.user, pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserMountSerializer(mount).data)
