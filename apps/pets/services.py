import logging
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.rpg.catalog_support import (
    available_pet_variants, egg_species, item_is_available,
    pet_is_available, potion_type_for_item,
)
from .lifecycle import GROWN_GROWTH, MIDDLE_GROWTH, companion_lifecycle_stage, growth_thresholds
from .roster import prepared_potion, prepared_family

logger = logging.getLogger(__name__)


class IncubationError(ValueError):
    """The requested change conflicts with an accepted incubation."""


class IncubationNotFound(ValueError):
    """No incubation belongs to this caller at the requested identity."""


GROWTH_PREFERRED_FOOD = 15
GROWTH_NEUTRAL_FOOD = 5
EVOLUTION_THRESHOLD = GROWN_GROWTH
BIRD_FLEDGLING_THRESHOLD = MIDDLE_GROWTH

# Daily cap on direct-grant growth from consumables (growth_surge,
# feast_platter). Tonic-doubled feeds are NOT capped here — those still
# require food items to exist, which is a natural limiter. Without this
# cap a kid could fully evolve a pet (0 → 100) in one sitting by stacking
# 3-4 hoarded surges; the design intent is real-world weeks of bonding.
# Tunable per the gentle-nudge doctrine — bumping the cap doesn't break
# anything, just lets evolution happen faster on heavy-consumable days.
CONSUMABLE_GROWTH_DAILY_CAP = 50

# Companion pet passive growth per daily check-in. Small on purpose —
# a Companion reaches evolution (100) in ~50 consecutive active days,
# longer with streak breaks. Grows the slow-burn-bonding feel.
COMPANION_DAILY_GROWTH = 2
COMPANION_SPECIES_SLUG = "companion"

# Pet happiness thresholds — days since last feed. Values are tuned so a
# kid who feeds their pet weekly never drops below 'bored', and a hard
# 'away' state only appears when a pet has been ignored long enough that
# the dashboard surface genuinely benefits from gently pointing it out.
# Gentle-nudge doctrine: happiness level is PURELY visual — it never
# penalizes coins, XP, drops, or growth progress.
HAPPINESS_THRESHOLDS = {
    "happy": 3,   # fed in the last 3 days
    "bored": 7,   # fed in the last 7 days
    "stale": 14,  # fed in the last 14 days
    # > 14 days → "away"
}


def bird_evolution_stage(companion, *, is_mount=False):
    """Read-only artwork stage for the exact prepared Base Chick identity.

    Growth and the existing evolution flag persist the selection. The
    intermediate artwork grants no new pet, mount, eligibility or reward;
    even a legacy 100-growth row needs confirmed evolution to select Bird.
    Other species/artwork/potion variants retain their existing presentation.
    """
    if (
        companion.species.slug != "chick"
        or companion.species.sprite_key != "cute-chick"
        or companion.potion.slug != "base"
    ):
        return None
    if is_mount or companion.evolved_to_mount:
        return "bird"
    return "fledgling" if companion.growth_points >= BIRD_FLEDGLING_THRESHOLD else "chick"


def happiness_for_pet(pet):
    """Bucket a UserPet into 'happy' / 'bored' / 'stale' / 'away'.

    Evolved pets always read as 'happy' — they're past the feeding loop.
    Pets with no feed history (just hatched) read as 'happy' for a grace
    window until their ``last_fed_at`` is set on first feed. Falls back
    on ``created_at`` if ``last_fed_at`` is still null, so an unfed pet
    sitting in the stable still decays visually instead of staying happy
    forever.
    """
    if getattr(pet, "evolved_to_mount", False):
        return "happy"
    reference = pet.last_fed_at or pet.created_at
    if reference is None:
        return "happy"
    delta_days = (timezone.now() - reference).days
    if delta_days <= HAPPINESS_THRESHOLDS["happy"]:
        return "happy"
    if delta_days <= HAPPINESS_THRESHOLDS["bored"]:
        return "bored"
    if delta_days <= HAPPINESS_THRESHOLDS["stale"]:
        return "stale"
    return "away"


class PetService:
    """Manages pet lifecycle: hatching, feeding, evolution, activation."""

    @staticmethod
    def _evaluate_pet_badges(user):
        from apps.achievements.services import BadgeService
        from apps.notifications.services import defer_push_until_commit, notify

        badges = BadgeService.evaluate_badges(user, scopes={"pet", "badges"})
        if not badges:
            return
        # Keep the authoritative award even if its optional notification fails.
        # Push delivery waits until ownership and the badge payout commit.
        try:
            with transaction.atomic(), defer_push_until_commit():
                for badge in badges:
                    notify(
                        user, title=f"Badge earned: {badge.name}", message=badge.description,
                        notification_type="badge_earned", link="/atlas?tab=badges",
                    )
        except Exception:
            logger.exception("Pet badge notification failed")

    @staticmethod
    def _save_growth(pet, *, update_fields):
        """Persist growth and its evolution together for an already locked pet.

        Growth callers hold the user gate before profile, pet and inventory
        locks. Keeping this transition shared means food, direct consumables
        and passive growth create the same mount and first-evolution effects.
        """
        from apps.pets.models import UserMount

        _middle, grown = growth_thresholds(pet)
        evolving = pet.growth_points >= grown and not pet.evolved_to_mount
        if evolving:
            pet.evolved_to_mount = True
        pet.save(update_fields=[*update_fields, "evolved_to_mount", "updated_at"])
        if not evolving:
            return None

        mount, created = UserMount.objects.get_or_create(
            user=pet.user, species=pet.species, potion=pet.potion,
        )
        PetService._evaluate_pet_badges(pet.user)
        if not created:
            return mount
        user = pet.user
        logger.info("User %s evolved %s %s to mount", user.username, pet.potion.name, pet.species.name)
        try:
            from apps.chronicle.services import ChronicleService
            with transaction.atomic():
                ChronicleService.record_first(
                    user,
                    event_slug="first_mount_evolved",
                    title=f"First mount \u2014 {pet.species.name}",
                    icon_slug="mount-sigil",
                    related=("usermount", mount.pk),
                )
        except Exception:
            logger.exception("Chronicle hook failed in pet evolution")

        try:
            from apps.notifications.services import notify, notify_parents
            with transaction.atomic():
                msg = f"{pet.potion.name} {pet.species.name} is ready to ride."
                notify(
                    user, title=f"{pet.species.name} evolved into a mount!", message=msg,
                    notification_type="pet_evolved", link="/bestiary?tab=mounts",
                )
                notify_parents(
                    title=f"{user.display_name or user.username}'s pet evolved",
                    message=msg, notification_type="pet_evolved", about_user=user,
                    link="/bestiary?tab=mounts",
                )
        except Exception:
            logger.exception("Notification hook failed in pet evolution")
        return mount

    @staticmethod
    def incubation_duration_seconds():
        return settings.PET_INCUBATION_DURATION_SECONDS

    @staticmethod
    def current_incubation(user):
        from .models import PetIncubation
        return PetIncubation.objects.filter(user=user, hatched_at__isnull=True).first()

    @staticmethod
    @transaction.atomic
    def start_incubation(user, egg_item_id, potion_item_id, request_id):
        """Accept and consume one owned pair, once per caller's request UUID."""
        from apps.achievements.services import _lock_award_user
        from apps.rpg.models import ItemDefinition, UserInventory
        from apps.rpg.catalog_icons import item_catalog_icon
        from .models import PetIncubation, UserPet
        from .serializers import PetSpeciesSerializer, PotionTypeSerializer

        try:
            request_id = UUID(str(request_id))
            if any(isinstance(value, bool) or not str(value).isdigit() for value in (egg_item_id, potion_item_id)):
                raise ValueError
            egg_item_id, potion_item_id = int(egg_item_id), int(potion_item_id)
            if egg_item_id < 1 or potion_item_id < 1:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Positive egg_item_id, potion_item_id and a valid request_id UUID are required")

        # All companion progression serializes through the same user gate.
        _lock_award_user(user)
        previous = PetIncubation.objects.filter(user=user, request_id=request_id).first()
        if previous:
            if (previous.accepted_pair["egg"]["id"], previous.accepted_pair["potion"]["id"]) != (egg_item_id, potion_item_id):
                raise IncubationError("This request_id was already used for a different egg and potion")
            return previous, False
        if PetIncubation.objects.filter(user=user, hatched_at__isnull=True).exists():
            raise IncubationError("Finish hatching your current egg before starting another incubation")

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
        species = egg_species(egg_item)
        if species is None:
            raise ValueError("Unknown or invalid companion egg binding")
        potion_type = potion_type_for_item(potion_item)
        if potion_type is None:
            raise ValueError("Unknown potion variant")
        registered_species = prepared_family(species) or (
            species.slug == "chick" and species.sprite_key == "cute-chick"
            and potion_type.slug in {"fire", "ice"}
        )
        if registered_species and not prepared_potion(potion_item):
            raise ValueError("This companion requires a registered global potion")

        # Authored species can restrict their supported variants. An empty
        # relation preserves unrestricted hatching for legacy species that
        # predate the content loader's compatibility data.
        available_potions = species.available_potions
        if available_potions.exists() and not available_potions.filter(pk=potion_type.pk).exists():
            raise ValueError(f"{species.name} cannot hatch with a {potion_type.name} potion")
        if not pet_is_available(species, potion_type) or not item_is_available(egg_item) or not item_is_available(potion_item):
            raise ValueError("This companion is not available to hatch with the current artwork. Your saved ingredients are unchanged.")

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

        def ingredient_snapshot(item):
            return {
                "id": item.pk, "slug": item.slug, "name": item.display_name,
                "icon": item.icon, "sprite_key": item.sprite_key,
                "rarity": item.rarity, "item_type": item.item_type,
                "catalog_icon": item_catalog_icon(item),
            }

        now = timezone.now()
        incubation = PetIncubation.objects.create(
            user=user, request_id=request_id, species=species, potion_type=potion_type,
            egg_item=egg_item, potion_item=potion_item,
            accepted_pair={
                "egg": ingredient_snapshot(egg_item), "potion": ingredient_snapshot(potion_item),
                "species": dict(PetSpeciesSerializer(species).data),
                "potion_type": dict(PotionTypeSerializer(potion_type).data),
            },
            started_at=now, ready_at=now + timedelta(seconds=PetService.incubation_duration_seconds()),
        )
        return incubation, True

    @staticmethod
    @transaction.atomic
    def hatch_incubation(user, incubation_id):
        """Explicitly hatch an accepted, ready pair; retries return its saved pet."""
        from apps.achievements.services import _lock_award_user
        from .models import PetIncubation, UserPet

        _lock_award_user(user)
        try:
            incubation = PetIncubation.objects.select_for_update(of=("self",)).select_related("species", "potion_type", "pet").get(pk=incubation_id, user=user)
        except PetIncubation.DoesNotExist:
            raise IncubationNotFound("Egg incubation not found")
        if incubation.hatched_at is not None:
            if incubation.pet_id is None:
                raise IncubationError("This egg has already hatched and its saved pet is no longer available")
            return incubation, incubation.pet, False
        now = timezone.now()
        if incubation.ready_at > now:
            raise IncubationError("Your egg is still incubating")

        # This pair was accepted and paid for at start. Catalog retirement or
        # compatibility edits cannot revoke that promise or consume more items.
        pet, created = UserPet.objects.get_or_create(user=user, species=incubation.species, potion=incubation.potion_type)
        incubation.pet = pet
        incubation.hatched_at = now
        incubation.save(update_fields=["pet", "hatched_at", "updated_at"])
        if not created:
            return incubation, pet, False
        PetService._evaluate_pet_badges(user)
        logger.info("User %s hatched accepted incubation %s", user.username, incubation.pk)

        # Chronicle hook — wrapped so a chronicle failure never breaks hatching.
        try:
            from apps.chronicle.services import ChronicleService
            with transaction.atomic():
                ChronicleService.record_first(
                    user, event_slug="first_pet_hatched",
                    title=f"Hatched your first pet \u2014 {incubation.accepted_pair['species']['name']}",
                    icon_slug="egg-crack", related=("userpet", pet.pk),
                )
        except Exception:
            logger.exception("Chronicle hook failed in hatch_incubation")
        return incubation, pet, True

    @staticmethod
    @transaction.atomic
    def auto_grow_companions(user):
        """Grow every unevolved Companion pet the user owns by a small amount.

        Fired from StreakService.record_activity on the first-today path so
        Companion pets gain +2 growth per active day. Evolves automatically
        when the growth threshold is reached; identical to a food-fed
        evolution (creates a UserMount row).

        Returns a dict summarizing the action plus an ``events`` list that
        feeds the companion-growth toast surface on the frontend. Each
        event also appends to ``CharacterProfile.pending_companion_growth``
        so a returning user catches up on every tick they missed without
        polling the daily check-in itself.

        Never raises — missing species, no pets, etc. all return cleanly
        so the streak flow stays robust.
        """
        from apps.achievements.services import _lock_award_user
        from apps.pets.models import UserPet, PetSpecies
        from apps.rpg.models import CharacterProfile

        _lock_award_user(user)
        try:
            species = PetSpecies.objects.get(slug=COMPANION_SPECIES_SLUG)
        except PetSpecies.DoesNotExist:
            return {
                "pets_grown": 0,
                "evolved": 0,
                "events": [],
                "reason": "no_companion_species",
            }

        profile, _ = CharacterProfile.objects.select_for_update().get_or_create(user=user)
        pets = list(
            UserPet.objects.select_for_update().filter(
                user=user, species=species, evolved_to_mount=False,
            ).order_by("pk")
        )
        events = []
        evolved = 0
        for pet in pets:
            new_growth = min(
                pet.growth_points + COMPANION_DAILY_GROWTH, EVOLUTION_THRESHOLD,
            )
            growth_added = new_growth - pet.growth_points
            pet.growth_points = new_growth
            event = {
                "pet_id": pet.pk,
                "species_slug": pet.species.slug,
                "species_name": pet.species.name,
                "species_sprite_key": pet.species.sprite_key,
                "species_icon": pet.species.icon,
                "potion_slug": pet.potion.slug,
                "potion_name": pet.potion.name,
                "growth_added": growth_added,
                "new_growth": new_growth,
                "evolved": False,
                "mount_id": None,
            }
            mount = PetService._save_growth(pet, update_fields=["growth_points"])
            if mount:
                evolved += 1
                event["evolved"] = True
                event["mount_id"] = mount.pk
            event["lifecycle_stage"] = companion_lifecycle_stage(pet)
            events.append(event)

        if events:
            # Append to the per-user pending queue so the frontend can
            # surface a toast on next page load. Use update_fields to avoid
            # racing with other CharacterProfile writers in the same flow.
            try:
                pending = list(profile.pending_companion_growth or [])
                pending.extend(events)
                profile.pending_companion_growth = pending
                profile.save(update_fields=["pending_companion_growth", "updated_at"])
            except Exception:
                logger.exception("Failed to persist companion-growth pending queue")

        return {
            "pets_grown": len(pets),
            "evolved": evolved,
            "growth_per_pet": COMPANION_DAILY_GROWTH,
            "events": events,
        }

    @staticmethod
    @transaction.atomic
    def feed_pet(user, pet_id, food_item_id):
        """Feed a food item to a pet, increasing growth points.

        Returns dict with: growth_added, new_growth, evolved (bool), mount (if evolved).
        """
        from apps.achievements.services import _lock_award_user
        from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
        from apps.pets.models import UserPet

        _lock_award_user(user)
        profile, _ = CharacterProfile.objects.select_for_update().get_or_create(user=user)

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
        from apps.rpg.item_effects import PREFERRED_FOOD_BONUS, food_base_growth
        growth = food_base_growth(food_item) + (PREFERRED_FOOD_BONUS if is_preferred else 0)
        if profile.pet_growth_boost_remaining > 0:
            growth *= 2
            profile.pet_growth_boost_remaining -= 1
            profile.save(update_fields=["pet_growth_boost_remaining", "updated_at"])

        # Consume food
        food_inv.quantity -= 1
        if food_inv.quantity == 0:
            food_inv.delete()
        else:
            food_inv.save(update_fields=["quantity", "updated_at"])

        # Apply growth and stamp last-fed for the happiness computation.
        pet.growth_points = min(pet.growth_points + growth, EVOLUTION_THRESHOLD)
        pet.last_fed_at = timezone.now()
        mount = PetService._save_growth(pet, update_fields=["growth_points", "last_fed_at"])

        return {
            "growth_added": growth,
            "new_growth": pet.growth_points,
            "evolved": mount is not None,
            "mount_id": mount.pk if mount else None,
            "evolution_stage": bird_evolution_stage(pet),
            "lifecycle_stage": companion_lifecycle_stage(pet),
        }

    @staticmethod
    @transaction.atomic
    def set_active_pet(user, pet_id):
        """Set a pet as the user's active pet (deactivates current)."""
        from apps.achievements.services import _lock_award_user
        from apps.pets.models import UserPet

        # Feast locks the stable in primary-key order. Serialize before the
        # current-pet update so activation cannot own those rows in reverse.
        _lock_award_user(user)
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
        from django.db.models import Prefetch
        from apps.pets.models import (
            MountExpedition, PetSpecies, UserMount, UserPet,
        )

        pets = list(UserPet.objects.filter(user=user).select_related("species", "potion").order_by("-is_active", "species__name", "pk"))
        # Same prefetch as MountsView — keep ``UserMountSerializer``'s
        # active-expedition lookup at O(2 queries) regardless of mount count.
        mounts = list(
            UserMount.objects
            .filter(user=user)
            .select_related("species", "potion")
            .order_by("-is_active", "species__name", "pk")
            .prefetch_related(Prefetch(
                "expeditions",
                queryset=MountExpedition.objects.filter(
                    status=MountExpedition.Status.ACTIVE,
                ).order_by("-started_at"),
                to_attr="prefetched_active_expeditions",
            ))
        )
        total_possible = sum(available_pet_variants(species).count() for species in PetSpecies.objects.all())

        return {
            "pets": pets,
            "mounts": mounts,
            "total_pets": len(pets),
            "total_mounts": len(mounts),
            "total_possible": total_possible,
            "breeding_available": False,
        }
