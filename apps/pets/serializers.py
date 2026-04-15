from rest_framework import serializers
from .models import PetSpecies, PotionType, UserPet, UserMount


class PetSpeciesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetSpecies
        fields = ["id", "name", "icon", "sprite_key", "description", "food_preference"]
        read_only_fields = fields


class PotionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PotionType
        fields = ["id", "name", "sprite_key", "color_hex", "rarity", "description"]
        read_only_fields = fields


class PotionTypeMiniSerializer(serializers.ModelSerializer):
    """Compact potion info for the species catalog BottomSheet."""
    class Meta:
        model = PotionType
        fields = ["id", "name", "color_hex", "rarity"]
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


class UserPetSerializer(serializers.ModelSerializer):
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)
    is_fully_grown = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserPet
        fields = [
            "id", "species", "potion", "name", "growth_points",
            "is_active", "evolved_to_mount", "is_fully_grown",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class UserMountSerializer(serializers.ModelSerializer):
    species = PetSpeciesSerializer(read_only=True)
    potion = PotionTypeSerializer(read_only=True)

    class Meta:
        model = UserMount
        fields = [
            "id", "species", "potion", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = fields
