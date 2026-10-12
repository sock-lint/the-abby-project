import math
from datetime import timedelta

from django.utils import timezone
from django.utils.functional import cached_property
from rest_framework import serializers
from .models import MountExpedition, PetSpecies, PotionType, UserPet, UserMount
from .services import MOUNT_BREEDING_COOLDOWN_DAYS


class PetSpeciesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetSpecies
        fields = ["id", "name", "icon", "sprite_key", "description", "food_preference"]
        read_only_fields = fields


class PotionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PotionType
        fields = ["id", "slug", "name", "sprite_key", "color_hex", "rarity", "description"]
        read_only_fields = fields


class PotionTypeMiniSerializer(serializers.ModelSerializer):
    """Compact potion info for the species catalog BottomSheet."""
    class Meta:
        model = PotionType
        fields = ["id", "slug", "name", "color_hex", "rarity"]
        read_only_fields = fields


class PetSpeciesCatalogSerializer(serializers.ModelSerializer):
    """Parent-only catalog view — includes compatible potion list."""
    available_potions = PotionTypeMiniSerializer(many=True, read_only=True)

    class Meta:
        model = PetSpecies
        fields = [
            "id", "name", "icon", "sprite_key", "description", "food_preference",
            "available_potions",
        ]
        read_only_fields = fields


class PetCodexEntrySerializer(serializers.ModelSerializer):
    """Child-readable codex entry — species + per-user ownership state.

    ``discovered`` flips true once the user has ever owned a pet OR mount of
    this species (set on the view, not computed here). ``owned_mount_potion_ids``
    lets the frontend illuminate the right tile in the 6-potion evolution row.
    """
    slug = serializers.CharField(read_only=True)
    available_potions = PotionTypeMiniSerializer(many=True, read_only=True)
    discovered = serializers.BooleanField(read_only=True)
    owned_pet_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True
    )
    owned_mount_potion_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True
    )

    class Meta:
        model = PetSpecies
        fields = [
            "id", "slug", "name", "icon", "sprite_key", "description",
            "food_preference", "available_potions",
            "discovered", "owned_pet_ids", "owned_mount_potion_ids",
        ]
        read_only_fields = fields


class UserPetSerializer(serializers.ModelSerializer):
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)
    is_fully_grown = serializers.BooleanField(read_only=True)
    happiness_level = serializers.CharField(read_only=True)

    class Meta:
        model = UserPet
        fields = [
            "id", "species", "potion", "name", "growth_points",
            "is_active", "evolved_to_mount", "is_fully_grown",
            "happiness_level", "last_fed_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class UserMountSerializer(serializers.ModelSerializer):
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)
    active_expedition = serializers.SerializerMethodField()
    can_breed = serializers.SerializerMethodField()
    breeding_cooldown_seconds = serializers.SerializerMethodField()

    class Meta:
        model = UserMount
        fields = [
            "id", "species", "potion", "is_active",
            "last_bred_at", "active_expedition", "can_breed", "breeding_cooldown_seconds",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    @cached_property
    def breeding_as_of(self):
        # Both fields share one server snapshot, including when the cooldown
        # deadline passes while a complete mount list is being serialized.
        return timezone.now()

    def get_breeding_cooldown_seconds(self, obj):
        if obj.last_bred_at is None:
            return 0
        ready_at = obj.last_bred_at + timedelta(days=MOUNT_BREEDING_COOLDOWN_DAYS)
        return max(0, math.ceil((ready_at - self.breeding_as_of).total_seconds()))

    def get_can_breed(self, obj):
        # Mirrors the existing cooldown rule. An active expedition does not
        # change breeding eligibility in the authoritative service.
        return self.get_breeding_cooldown_seconds(obj) == 0

    def get_active_expedition(self, obj):
        """Compact summary of this mount's currently-running expedition.

        Returns None when the mount has no active row; the frontend uses
        this to flip the mount card into out-on-expedition state without
        a second API call.

        Optimization: when the view prefetches active expeditions onto
        ``obj.prefetched_active_expeditions`` (see ``MountsView`` /
        ``StableView``), we read the list directly and avoid a per-mount
        DB hit. Falls back to a query when the attribute is absent so the
        serializer keeps working in admin / tests / one-off callers.
        """
        prefetched = getattr(obj, "prefetched_active_expeditions", None)
        if prefetched is not None:
            active = prefetched[0] if prefetched else None
        else:
            active = (
                MountExpedition.objects
                .filter(mount=obj, status=MountExpedition.Status.ACTIVE)
                .order_by("-started_at")
                .first()
            )
        if active is None:
            return None
        return MountExpeditionSerializer(active).data


class MountExpeditionSerializer(serializers.ModelSerializer):
    is_ready = serializers.BooleanField(read_only=True)
    seconds_remaining = serializers.IntegerField(read_only=True)
    mount_id = serializers.IntegerField(source="mount.pk", read_only=True)
    species_name = serializers.CharField(source="mount.species.name", read_only=True)
    species_slug = serializers.CharField(source="mount.species.slug", read_only=True)
    species_sprite_key = serializers.CharField(source="mount.species.sprite_key", read_only=True)
    species_icon = serializers.CharField(source="mount.species.icon", read_only=True)
    potion_name = serializers.CharField(source="mount.potion.name", read_only=True)
    potion_slug = serializers.CharField(source="mount.potion.slug", read_only=True)

    class Meta:
        model = MountExpedition
        fields = [
            "id", "mount_id", "tier", "status",
            "started_at", "returns_at", "claimed_at",
            "is_ready", "seconds_remaining",
            "species_name", "species_slug", "species_sprite_key",
            "species_icon", "potion_name", "potion_slug",
            "loot",
        ]
        read_only_fields = fields
