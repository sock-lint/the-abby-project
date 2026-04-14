from django.contrib import admin

from .models import PetSpecies, PotionType, UserMount, UserPet


@admin.register(PetSpecies)
class PetSpeciesAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "food_preference")


@admin.register(PotionType)
class PotionTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "color_hex", "rarity")


@admin.register(UserPet)
class UserPetAdmin(admin.ModelAdmin):
    list_display = ("user", "species", "potion", "growth_points", "is_active", "evolved_to_mount")
    list_filter = ("is_active", "evolved_to_mount", "species")


@admin.register(UserMount)
class UserMountAdmin(admin.ModelAdmin):
    list_display = ("user", "species", "potion", "is_active")
    list_filter = ("is_active", "species")
