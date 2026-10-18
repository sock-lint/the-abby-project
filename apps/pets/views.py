from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from apps.rpg.catalog_support import available_pet_variants, pet_is_available, potion_is_available

from .expeditions import ExpeditionError, ExpeditionNotFound, ExpeditionService
from .models import PetSpecies, PotionType, UserPet, UserMount
from .serializers import (
    MountExpeditionSerializer,
    PetCodexEntrySerializer,
    PetSpeciesCatalogSerializer,
    PotionTypeSerializer,
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
            "breeding_available": stable["breeding_available"],
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
        from django.db.models import Prefetch
        from .models import MountExpedition

        # Prefetch active expeditions onto each mount so
        # ``UserMountSerializer.get_active_expedition`` doesn't N+1 the
        # mount list — at one mount + one query each pre-prefetch, a kid
        # with 20+ mounts saw a 40+ query response. With the prefetch
        # the cost collapses to two queries total.
        mounts = (
            UserMount.objects
            .filter(user=request.user)
            .select_related("species", "potion")
            .prefetch_related(Prefetch(
                "expeditions",
                queryset=MountExpedition.objects.filter(
                    status=MountExpedition.Status.ACTIVE,
                ).order_by("-started_at"),
                to_attr="prefetched_active_expeditions",
            ))
        )
        return Response(UserMountSerializer(mounts, many=True).data)


class PetSpeciesCatalogView(ListAPIView):
    """GET /api/pets/species/catalog/ — parent-only browse of supported species."""
    permission_classes = [permissions.IsAuthenticated, IsParent]
    serializer_class = PetSpeciesCatalogSerializer
    pagination_class = None

    def get_queryset(self):
        return [species for species in PetSpecies.objects.prefetch_related("available_potions").order_by("name") if pet_is_available(species)]


class PetCodexView(APIView):
    """GET /api/pets/codex/ — child-readable bestiary codex.

    Returns supported species and potions with the requesting user's exact
    ownership state. Saved legacy ownership remains in the stable response.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        species_qs = [species for species in PetSpecies.objects.prefetch_related("available_potions").order_by("name") if pet_is_available(species)]

        owned_pets = [(pet.species_id, pet.pk) for pet in UserPet.objects.filter(user=user).select_related("species", "potion")
                      if pet_is_available(pet.species, pet.potion)]
        owned_mounts = [(mount.species_id, mount.potion_id) for mount in UserMount.objects.filter(user=user).select_related("species", "potion")
                        if pet_is_available(mount.species, mount.potion)]

        pets_by_species = {}
        for species_id, pet_id in owned_pets:
            pets_by_species.setdefault(species_id, []).append(pet_id)

        mount_potions_by_species = {}
        for species_id, potion_id in owned_mounts:
            mount_potions_by_species.setdefault(species_id, []).append(potion_id)

        entries = []
        discovered_count = 0
        for species in species_qs:
            owned_pet_ids = pets_by_species.get(species.id, [])
            owned_mount_potion_ids = mount_potions_by_species.get(species.id, [])
            discovered = bool(owned_pet_ids or owned_mount_potion_ids)
            if discovered:
                discovered_count += 1
            species.discovered = discovered
            species.owned_pet_ids = owned_pet_ids
            species.owned_mount_potion_ids = owned_mount_potion_ids
            entries.append(species)

        potions_qs = [potion for potion in PotionType.objects.order_by("rarity", "name") if potion_is_available(potion)]
        total_species = len(entries)
        mounts_possible = sum(available_pet_variants(species).count() for species in entries)

        return Response({
            "species": PetCodexEntrySerializer(entries, many=True).data,
            "potions": PotionTypeSerializer(potions_qs, many=True).data,
            "totals": {
                "species": total_species,
                "discovered_species": discovered_count,
                "mounts_possible": mounts_possible,
                "mounts_owned": len(owned_mounts),
            },
        })


class ActivateMountView(APIView):
    """POST /api/mounts/{id}/activate/ — set as active mount."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            mount = PetService.set_active_mount(request.user, pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserMountSerializer(mount).data)


class CompanionGrowthRecentView(APIView):
    """GET /api/pets/companion-growth/recent/ — unseen passive growth events.

    Returns the queue stashed on ``CharacterProfile.pending_companion_growth``
    by ``PetService.auto_grow_companions``. The frontend toast hook polls
    this and POSTs to ``/seen/`` once it's rendered the events. Self-scoped
    to ``request.user`` — never reveals another household's growth feed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.rpg.models import CharacterProfile
        profile = CharacterProfile.objects.filter(user=request.user).first()
        events = list(profile.pending_companion_growth or []) if profile else []
        return Response({"events": events})


class CompanionGrowthSeenView(APIView):
    """POST /api/pets/companion-growth/seen/ — clear the pending queue.

    Idempotent: an empty queue stays empty, calling twice is harmless.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.rpg.models import CharacterProfile
        profile, _ = CharacterProfile.objects.get_or_create(user=request.user)
        if profile.pending_companion_growth:
            profile.pending_companion_growth = []
            profile.save(update_fields=["pending_companion_growth", "updated_at"])
        return Response({"cleared": True})


class BreedMountsView(APIView):
    """Authenticated tombstone for the retired breeding endpoint."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(
            {"error": "Pet breeding has been removed."},
            status=status.HTTP_410_GONE,
        )


class StartExpeditionView(APIView):
    """POST /api/mounts/<id>/expedition/ — send the mount on an offline run.

    Body: ``{"tier": "short" | "standard" | "long"}``. Returns the new
    expedition row, including the locked loot preview the frontend uses
    to render the in-flight card.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        tier = request.data.get("tier")
        if tier not in ("short", "standard", "long"):
            return Response(
                {"error": "tier must be one of 'short', 'standard', 'long'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            expedition = ExpeditionService.start(request.user, pk, tier)
        except ExpeditionNotFound as exc:
            # Cross-user / unknown mount → 404 to avoid leaking whether a
            # mount with that pk exists in another household. Branch on the
            # exception class, not the message text.
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ExpeditionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            MountExpeditionSerializer(expedition).data,
            status=status.HTTP_201_CREATED,
        )


class ListExpeditionsView(APIView):
    """GET /api/expeditions/[?ready=true] — every expedition for the user.

    The optional ``ready=true`` filter is what the toast-stack hook uses to
    poll for unclaimed loot — it returns only active expeditions whose
    ``returns_at`` has passed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ready_only = str(request.query_params.get("ready", "")).lower() in {"1", "true", "yes"}
        expeditions = ExpeditionService.list_for_user(request.user, ready_only=ready_only)
        return Response({
            "expeditions": MountExpeditionSerializer(expeditions, many=True).data,
        })


class ClaimExpeditionView(APIView):
    """POST /api/expeditions/<id>/claim/ — materialize loot into ledger + inventory.

    Idempotent: a second claim returns the first claim's serialized result
    with ``coins_awarded=0`` and ``freshly_claimed=False``. Cross-user
    expedition pks return 404 (existence-leak prevention).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            result = ExpeditionService.claim(request.user, pk)
        except ExpeditionNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ExpeditionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
