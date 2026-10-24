import math

from django.utils import timezone
from django.utils.functional import cached_property
from rest_framework import serializers
from .models import MountExpedition, PetIncubation, PetSpecies, PotionType, UserPet, UserMount
from .lifecycle import LIFECYCLE_STAGES, companion_lifecycle_stage
from .rarity import companion_rarity
from .services import bird_evolution_stage
from .expeditions import expedition_day_bounds
from apps.rpg.coin_policy import EXPEDITION_DAILY_LIMIT
from apps.rpg.catalog_support import available_pet_variants, pet_is_available, potion_is_available
from apps.rpg.catalog_icons import species_catalog_icon


class CatalogPortraitFields:
    def get_lifecycle_stages(self, obj):
        return list(LIFECYCLE_STAGES)

    def get_catalog_icon(self, obj):
        return species_catalog_icon(obj)

    def get_grown_catalog_icon(self, obj):
        return species_catalog_icon(obj, grown=True)


class PetSpeciesSerializer(CatalogPortraitFields, serializers.ModelSerializer):
    lifecycle_stages = serializers.SerializerMethodField()
    catalog_icon = serializers.SerializerMethodField()
    grown_catalog_icon = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    class Meta:
        model = PetSpecies
        fields = ["id", "slug", "name", "icon", "sprite_key", "description", "rarity", "food_preference", "catalog_available", "catalog_icon", "grown_catalog_icon", "lifecycle_stages"]
        read_only_fields = fields

    def get_catalog_available(self, obj):
        return pet_is_available(obj)


class PotionTypeSerializer(serializers.ModelSerializer):
    catalog_available = serializers.SerializerMethodField()
    class Meta:
        model = PotionType
        fields = ["id", "slug", "name", "sprite_key", "color_hex", "rarity", "description", "catalog_available"]
        read_only_fields = fields

    def get_catalog_available(self, obj):
        return potion_is_available(obj)


class StartIncubationSerializer(serializers.Serializer):
    egg_item_id = serializers.IntegerField(min_value=1)
    potion_item_id = serializers.IntegerField(min_value=1)
    request_id = serializers.UUIDField()


class PetIncubationSerializer(serializers.ModelSerializer):
    egg = serializers.JSONField(source="accepted_pair.egg", read_only=True)
    potion = serializers.JSONField(source="accepted_pair.potion", read_only=True)
    species = serializers.JSONField(source="accepted_pair.species", read_only=True)
    potion_type = serializers.JSONField(source="accepted_pair.potion_type", read_only=True)
    remaining_seconds = serializers.SerializerMethodField()
    is_ready = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    pet_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = PetIncubation
        fields = ["id", "egg", "potion", "species", "potion_type", "started_at", "ready_at", "remaining_seconds", "is_ready", "status", "hatched_at", "pet_id"]
        read_only_fields = fields

    @cached_property
    def as_of(self):
        return self.context.get("as_of") or timezone.now()

    def get_remaining_seconds(self, obj):
        if obj.hatched_at is not None:
            return 0
        return max(0, math.ceil((obj.ready_at - self.as_of).total_seconds()))

    def get_is_ready(self, obj):
        return obj.hatched_at is None and obj.ready_at <= self.as_of

    def get_status(self, obj):
        if obj.hatched_at is not None:
            return "hatched"
        return "ready" if self.get_is_ready(obj) else "incubating"


class PotionTypeMiniSerializer(serializers.ModelSerializer):
    """Compact potion info for the species catalog BottomSheet."""
    class Meta:
        model = PotionType
        fields = ["id", "slug", "name", "color_hex", "rarity"]
        read_only_fields = fields


class CodexPotionSerializer(PotionTypeMiniSerializer):
    acquisition_challenges = serializers.SerializerMethodField()

    class Meta(PotionTypeMiniSerializer.Meta):
        fields = [*PotionTypeMiniSerializer.Meta.fields, "acquisition_challenges"]

    def get_acquisition_challenges(self, obj):
        return self.context.get("acquisition_challenges", {}).get((self.context.get("species_id"), obj.pk), [])


class PetSpeciesCatalogSerializer(CatalogPortraitFields, serializers.ModelSerializer):
    """Parent-only catalog view — includes compatible potion list."""
    available_potions = serializers.SerializerMethodField()
    lifecycle_stages = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    catalog_icon = serializers.SerializerMethodField()
    grown_catalog_icon = serializers.SerializerMethodField()

    class Meta:
        model = PetSpecies
        fields = [
            "id", "name", "icon", "sprite_key", "description", "rarity", "food_preference",
            "available_potions", "catalog_available", "catalog_icon", "grown_catalog_icon", "lifecycle_stages",
        ]
        read_only_fields = fields

    def get_available_potions(self, obj):
        return PotionTypeMiniSerializer(available_pet_variants(obj), many=True).data

    def get_catalog_available(self, obj):
        return pet_is_available(obj)


class PetCodexEntrySerializer(CatalogPortraitFields, serializers.ModelSerializer):
    """Child-readable codex entry — species + per-user ownership state.

    ``discovered`` flips true once the user has ever owned a pet OR mount of
    this species (set on the view, not computed here). ``owned_mount_potion_ids``
    lets the frontend illuminate the right tile in the 6-potion evolution row.
    """
    slug = serializers.CharField(read_only=True)
    lifecycle_stages = serializers.SerializerMethodField()
    available_potions = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    catalog_icon = serializers.SerializerMethodField()
    grown_catalog_icon = serializers.SerializerMethodField()
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
            "id", "slug", "name", "icon", "sprite_key", "description", "rarity",
            "food_preference", "available_potions",
            "discovered", "owned_pet_ids", "owned_mount_potion_ids", "catalog_available", "catalog_icon", "grown_catalog_icon", "lifecycle_stages",
        ]
        read_only_fields = fields

    def get_available_potions(self, obj):
        return CodexPotionSerializer(available_pet_variants(obj), many=True, context={
            "species_id": obj.pk, "acquisition_challenges": self.context.get("acquisition_challenges", {}),
        }).data

    def get_catalog_available(self, obj):
        return pet_is_available(obj)


class UserPetSerializer(serializers.ModelSerializer):
    rarity = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    evolution_stage = serializers.SerializerMethodField()
    lifecycle_stage = serializers.SerializerMethodField()
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)
    is_fully_grown = serializers.BooleanField(read_only=True)
    happiness_level = serializers.CharField(read_only=True)

    class Meta:
        model = UserPet
        fields = [
            "id", "species", "potion", "rarity", "name", "growth_points",
            "is_active", "evolved_to_mount", "is_fully_grown",
            "happiness_level", "last_fed_at",
            "created_at", "updated_at", "catalog_available", "evolution_stage", "lifecycle_stage",
        ]
        read_only_fields = fields

    def get_rarity(self, obj):
        return companion_rarity(obj.species, obj.potion)

    def get_catalog_available(self, obj):
        return pet_is_available(obj.species, obj.potion)

    def get_evolution_stage(self, obj):
        return bird_evolution_stage(obj)

    def get_lifecycle_stage(self, obj):
        return companion_lifecycle_stage(obj)


class UserMountSerializer(serializers.ModelSerializer):
    rarity = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    evolution_stage = serializers.SerializerMethodField()
    lifecycle_stage = serializers.SerializerMethodField()
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)
    active_expedition = serializers.SerializerMethodField()
    can_breed = serializers.SerializerMethodField()
    breeding_cooldown_seconds = serializers.SerializerMethodField()
    expedition_available = serializers.SerializerMethodField()
    expedition_available_at = serializers.SerializerMethodField()
    expedition_available_in_seconds = serializers.SerializerMethodField()

    class Meta:
        model = UserMount
        fields = [
            "id", "species", "potion", "rarity", "is_active",
            "last_bred_at", "active_expedition", "can_breed", "breeding_cooldown_seconds",
            "expedition_available", "expedition_available_at", "expedition_available_in_seconds",
            "created_at", "updated_at", "catalog_available", "evolution_stage", "lifecycle_stage",
        ]
        read_only_fields = fields

    def get_rarity(self, obj):
        return companion_rarity(obj.species, obj.potion)

    def get_catalog_available(self, obj):
        return pet_is_available(obj.species, obj.potion)

    def get_evolution_stage(self, obj):
        return bird_evolution_stage(obj, is_mount=True)

    def get_lifecycle_stage(self, obj):
        return companion_lifecycle_stage(obj, is_mount=True)

    # Retained response fields keep older clients from offering a retired action.
    def get_breeding_cooldown_seconds(self, obj):
        return 0

    def get_can_breed(self, obj):
        return False

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
        active = self._active_expedition(obj)
        return MountExpeditionSerializer(active, context={"expedition_as_of": self.expedition_as_of}).data if active else None

    def _active_expedition(self, obj):
        # Reuse the active row across readiness and daily availability fields.
        if not hasattr(self, "_active_expeditions"):
            self._active_expeditions = {}
        if obj.pk in self._active_expeditions:
            return self._active_expeditions[obj.pk]
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
        self._active_expeditions[obj.pk] = active
        return active

    @cached_property
    def expedition_as_of(self):
        return timezone.now()

    def _expedition_bounds(self, obj):
        if not hasattr(self, "_expedition_bounds_by_owner"):
            self._expedition_bounds_by_owner = {}
        if obj.user_id not in self._expedition_bounds_by_owner:
            self._expedition_bounds_by_owner[obj.user_id] = expedition_day_bounds(obj.user, self.expedition_as_of)
        return self._expedition_bounds_by_owner[obj.user_id]

    def _expeditions_today(self, obj):
        if not hasattr(self, "_expedition_today_by_owner"):
            self._expedition_today_by_owner = {}
        if obj.user_id not in self._expedition_today_by_owner:
            day_start, next_day = self._expedition_bounds(obj)
            self._expedition_today_by_owner[obj.user_id] = list(
                MountExpedition.objects.filter(
                    mount__user_id=obj.user_id, started_at__gte=day_start, started_at__lt=next_day,
                ).values_list("mount__species_id", flat=True)
            )
        return self._expedition_today_by_owner[obj.user_id]

    def _expedition_used_today(self, obj):
        return obj.species_id in self._expeditions_today(obj)

    def _child_allowance_used(self, obj):
        return len(self._expeditions_today(obj)) >= EXPEDITION_DAILY_LIMIT

    def _species_has_active_expedition(self, obj):
        # An unclaimed trip on any potion appearance occupies this species'
        # slot. Keep active_expedition itself bound to the exact mount so
        # clients never mistake another appearance's receipt for their own.
        if not hasattr(self, "_active_expedition_species_by_owner"):
            self._active_expedition_species_by_owner = {}
        if obj.user_id not in self._active_expedition_species_by_owner:
            self._active_expedition_species_by_owner[obj.user_id] = set(
                MountExpedition.objects.filter(
                    mount__user_id=obj.user_id, status=MountExpedition.Status.ACTIVE,
                ).values_list("mount__species_id", flat=True)
            )
        return obj.species_id in self._active_expedition_species_by_owner[obj.user_id]

    def get_expedition_available(self, obj):
        return (not self._species_has_active_expedition(obj)
                and not self._expedition_used_today(obj) and not self._child_allowance_used(obj))

    def get_expedition_available_at(self, obj):
        # An unclaimed trip requires an explicit claim, so no timestamp can
        # promise another launch. Otherwise today's run resets at midnight.
        if self._species_has_active_expedition(obj):
            return None
        if not self._expedition_used_today(obj) and not self._child_allowance_used(obj):
            return None
        return serializers.DateTimeField().to_representation(self._next_expedition_day(obj))

    def _next_expedition_day(self, obj):
        return self._expedition_bounds(obj)[1]

    def get_expedition_available_in_seconds(self, obj):
        if self._species_has_active_expedition(obj):
            return None
        if not self._expedition_used_today(obj) and not self._child_allowance_used(obj):
            return 0
        return max(0, math.ceil((self._next_expedition_day(obj) - self.expedition_as_of).total_seconds()))


class MountExpeditionSerializer(serializers.ModelSerializer):
    is_ready = serializers.SerializerMethodField()
    seconds_remaining = serializers.SerializerMethodField()
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

    @cached_property
    def expedition_as_of(self):
        return self.context.get("expedition_as_of") or timezone.now()

    def get_is_ready(self, obj):
        return self.expedition_as_of >= obj.returns_at

    def get_seconds_remaining(self, obj):
        return int((obj.returns_at - self.expedition_as_of).total_seconds())
