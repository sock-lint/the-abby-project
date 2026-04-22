import logging

from django.db import transaction

logger = logging.getLogger(__name__)

GROWTH_PREFERRED_FOOD = 15
GROWTH_NEUTRAL_FOOD = 5
EVOLUTION_THRESHOLD = 100


class PetService:
    """Manages pet lifecycle: hatching, feeding, evolution, activation."""

    @staticmethod
    @transaction.atomic
    def hatch_pet(user, egg_item_id, potion_item_id):
        """Consume an egg + potion from inventory to create a new pet.

        Returns the new UserPet, or raises ValueError on invalid input.
        """
        from apps.rpg.models import ItemDefinition, UserInventory
        from apps.pets.models import PetSpecies, PotionType, UserPet

        # Validate egg
        try:
            egg_inv = UserInventory.objects.select_for_update().get(
                user=user, item_id=egg_item_id, quantity__gte=1,
            )
        except UserInventory.DoesNotExist:
            raise ValueError("You don't have that egg in your inventory")

        egg_item = egg_inv.item
        if egg_item.item_type != ItemDefinition.ItemType.EGG:
            raise ValueError("That item is not an egg")

        # Validate potion
        try:
            potion_inv = UserInventory.objects.select_for_update().get(
                user=user, item_id=potion_item_id, quantity__gte=1,
            )
        except UserInventory.DoesNotExist:
            raise ValueError("You don't have that potion in your inventory")

        potion_item = potion_inv.item
        if potion_item.item_type != ItemDefinition.ItemType.POTION:
            raise ValueError("That item is not a potion")

        # Prefer the typed FK; fall back to the legacy metadata slug for
        # any item rows that haven't been backfilled (e.g. during migration).
        species = egg_item.pet_species
        if species is None:
            species_key = str(egg_item.metadata.get("species", "")).strip()
            try:
                species = PetSpecies.objects.get(name__iexact=species_key)
            except PetSpecies.DoesNotExist:
                raise ValueError(f"Unknown species: {species_key}")

        potion_type = potion_item.potion_type
        if potion_type is None:
            variant_key = str(potion_item.metadata.get("variant", "")).strip()
            try:
                potion_type = PotionType.objects.get(name__iexact=variant_key)
            except PotionType.DoesNotExist:
                raise ValueError(f"Unknown potion variant: {variant_key}")

        # Check if user already has this combo
        if UserPet.objects.filter(user=user, species=species, potion=potion_type).exists():
            raise ValueError(f"You already have a {potion_type.name} {species.name}")

        # Consume items
        egg_inv.quantity -= 1
        if egg_inv.quantity == 0:
            egg_inv.delete()
        else:
            egg_inv.save(update_fields=["quantity", "updated_at"])

        potion_inv.quantity -= 1
        if potion_inv.quantity == 0:
            potion_inv.delete()
        else:
            potion_inv.save(update_fields=["quantity", "updated_at"])

        # Create the pet
        pet = UserPet.objects.create(
            user=user, species=species, potion=potion_type,
        )

        logger.info("User %s hatched %s %s", user.username, potion_type.name, species.name)

        # Chronicle hook — wrapped so a chronicle failure never breaks hatching.
        try:
            from apps.chronicle.services import ChronicleService
            ChronicleService.record_first(
                user,
                event_slug="first_pet_hatched",
                title=f"Hatched your first pet \u2014 {species.name}",
                icon_slug="egg-crack",
                related=("userpet", pet.pk),
            )
        except Exception:
            logger.exception("Chronicle hook failed in hatch_pet")

        return pet

    @staticmethod
    @transaction.atomic
    def feed_pet(user, pet_id, food_item_id):
        """Feed a food item to a pet, increasing growth points.

        Returns dict with: growth_added, new_growth, evolved (bool), mount (if evolved).
        """
        from apps.rpg.models import ItemDefinition, UserInventory
        from apps.pets.models import UserPet, UserMount

        try:
            pet = UserPet.objects.select_for_update().get(pk=pet_id, user=user)
        except UserPet.DoesNotExist:
            raise ValueError("Pet not found")

        if pet.evolved_to_mount:
            raise ValueError("This pet has already evolved into a mount")

        # Validate food
        try:
            food_inv = UserInventory.objects.select_for_update().get(
                user=user, item_id=food_item_id, quantity__gte=1,
            )
        except UserInventory.DoesNotExist:
            raise ValueError("You don't have that food in your inventory")

        food_item = food_inv.item
        if food_item.item_type != ItemDefinition.ItemType.FOOD:
            raise ValueError("That item is not food")

        # Calculate growth. Prefer the typed food_species FK; fall back to
        # the legacy metadata food_type string compare for unmigrated rows.
        is_preferred = False
        if food_item.food_species_id:
            is_preferred = food_item.food_species_id == pet.species_id
        else:
            food_type = str(food_item.metadata.get("food_type", "")).strip()
            if food_type and food_type == pet.species.food_preference:
                is_preferred = True
        growth = GROWTH_PREFERRED_FOOD if is_preferred else GROWTH_NEUTRAL_FOOD

        # Consume food
        food_inv.quantity -= 1
        if food_inv.quantity == 0:
            food_inv.delete()
        else:
            food_inv.save(update_fields=["quantity", "updated_at"])

        # Apply growth
        pet.growth_points = min(pet.growth_points + growth, EVOLUTION_THRESHOLD)
        pet.save(update_fields=["growth_points", "updated_at"])

        # Check evolution
        evolved = False
        mount = None
        if pet.growth_points >= EVOLUTION_THRESHOLD and not pet.evolved_to_mount:
            pet.evolved_to_mount = True
            pet.save(update_fields=["evolved_to_mount", "updated_at"])
            mount = UserMount.objects.create(
                user=user, species=pet.species, potion=pet.potion,
            )
            evolved = True
            logger.info("User %s evolved %s %s to mount", user.username, pet.potion.name, pet.species.name)

            # Chronicle hook — wrapped so a chronicle failure never breaks evolution.
            try:
                from apps.chronicle.services import ChronicleService
                ChronicleService.record_first(
                    user,
                    event_slug="first_mount_evolved",
                    title=f"First mount \u2014 {pet.species.name}",
                    icon_slug="mount-sigil",
                    related=("usermount", mount.pk),
                )
            except Exception:
                logger.exception("Chronicle hook failed in feed_pet evolve-to-mount")

        return {
            "growth_added": growth,
            "new_growth": pet.growth_points,
            "evolved": evolved,
            "mount_id": mount.pk if mount else None,
        }

    @staticmethod
    @transaction.atomic
    def set_active_pet(user, pet_id):
        """Set a pet as the user's active pet (deactivates current)."""
        from apps.pets.models import UserPet

        UserPet.objects.filter(user=user, is_active=True).update(is_active=False)
        try:
            pet = UserPet.objects.get(pk=pet_id, user=user)
        except UserPet.DoesNotExist:
            raise ValueError("Pet not found")
        pet.is_active = True
        pet.save(update_fields=["is_active", "updated_at"])
        return pet

    @staticmethod
    @transaction.atomic
    def set_active_mount(user, mount_id):
        """Set a mount as the user's active mount (deactivates current)."""
        from apps.pets.models import UserMount

        UserMount.objects.filter(user=user, is_active=True).update(is_active=False)
        try:
            mount = UserMount.objects.get(pk=mount_id, user=user)
        except UserMount.DoesNotExist:
            raise ValueError("Mount not found")
        mount.is_active = True
        mount.save(update_fields=["is_active", "updated_at"])
        return mount

    @staticmethod
    def get_stable(user):
        """Return all pets and mounts for a user, plus collection stats."""
        from apps.pets.models import PetSpecies, PotionType, UserPet, UserMount

        pets = list(UserPet.objects.filter(user=user).select_related("species", "potion"))
        mounts = list(UserMount.objects.filter(user=user).select_related("species", "potion"))
        total_species = PetSpecies.objects.count()
        total_potions = PotionType.objects.count()
        total_possible = total_species * total_potions

        return {
            "pets": pets,
            "mounts": mounts,
            "total_pets": len(pets),
            "total_mounts": len(mounts),
            "total_possible": total_possible,
        }
