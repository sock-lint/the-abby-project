import logging
import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

GROWTH_PREFERRED_FOOD = 15
GROWTH_NEUTRAL_FOOD = 5
EVOLUTION_THRESHOLD = 100

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

# Pet breeding — added 2026-04-23. Each mount can only be bred once per
# cooldown window. The chromatic-upgrade chance is the wildcard reward
# path: 1-in-50 rolls hand out the legendary Cosmic potion regardless
# of parent potions, so rare potion variants are earnable via stable
# husbandry in addition to drops.
MOUNT_BREEDING_COOLDOWN_DAYS = 7
CHROMATIC_UPGRADE_CHANCE = 0.02
CHROMATIC_POTION_SLUG = "cosmic"

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
        from apps.pets.models import UserPet, UserMount, PetSpecies
        from apps.rpg.models import CharacterProfile

        try:
            species = PetSpecies.objects.get(slug=COMPANION_SPECIES_SLUG)
        except PetSpecies.DoesNotExist:
            return {
                "pets_grown": 0,
                "evolved": 0,
                "events": [],
                "reason": "no_companion_species",
            }

        pets = list(
            UserPet.objects.select_for_update().filter(
                user=user, species=species, evolved_to_mount=False,
            )
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
            if pet.growth_points >= EVOLUTION_THRESHOLD:
                pet.evolved_to_mount = True
                pet.save(update_fields=[
                    "growth_points", "evolved_to_mount", "updated_at",
                ])
                mount, _ = UserMount.objects.get_or_create(
                    user=user, species=pet.species, potion=pet.potion,
                )
                evolved += 1
                event["evolved"] = True
                event["mount_id"] = mount.pk
            else:
                pet.save(update_fields=["growth_points", "updated_at"])
            events.append(event)

        if events:
            # Append to the per-user pending queue so the frontend can
            # surface a toast on next page load. Use update_fields to avoid
            # racing with other CharacterProfile writers in the same flow.
            try:
                profile, _ = CharacterProfile.objects.select_for_update().get_or_create(user=user)
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

        # Apply growth and stamp last-fed for the happiness computation.
        pet.growth_points = min(pet.growth_points + growth, EVOLUTION_THRESHOLD)
        pet.last_fed_at = timezone.now()
        pet.save(update_fields=["growth_points", "last_fed_at", "updated_at"])

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

            try:
                from apps.notifications.services import notify, notify_parents
                title = f"{pet.species.name} evolved into a mount!"
                msg = f"{pet.potion.name} {pet.species.name} is ready to ride."
                notify(
                    user, title=title, message=msg,
                    notification_type="pet_evolved",
                    link="/bestiary?tab=mounts",
                )
                notify_parents(
                    title=f"{user.display_name or user.username}'s pet evolved",
                    message=msg,
                    notification_type="pet_evolved",
                    about_user=user,
                    link="/bestiary?tab=mounts",
                )
            except Exception:
                logger.exception("Notification hook failed in feed_pet evolve-to-mount")

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
    @transaction.atomic
    def breed_mounts(user, mount_a_id, mount_b_id):
        """Combine two mature mounts to yield a hybrid egg + potion pair.

        Each parent mount enters a cooldown (``MOUNT_BREEDING_COOLDOWN_DAYS``)
        after breeding. The result is an egg of ONE parent's species (50/50)
        plus a potion of ONE parent's potion (50/50), both deposited into the
        user's inventory. A ``CHROMATIC_UPGRADE_CHANCE`` (1-in-50) wildcard
        overrides the picked potion with Cosmic — gives the stable-husbandry
        path a rare/legendary endpoint without relying on drops.

        Same-mount pairs raise ``ValueError`` (can't breed with yourself).
        Returns a dict summarizing the roll.
        """
        from apps.pets.models import UserMount
        from apps.rpg.models import ItemDefinition, UserInventory

        if mount_a_id == mount_b_id:
            raise ValueError("A mount can't breed with itself — pick two different mounts")

        try:
            mounts = list(
                UserMount.objects.select_for_update().select_related(
                    "species", "potion",
                ).filter(pk__in=[mount_a_id, mount_b_id], user=user)
            )
        except UserMount.DoesNotExist:
            raise ValueError("One or both mounts not found")
        if len(mounts) != 2:
            raise ValueError("One or both mounts not found")

        now = timezone.now()
        cooldown = timedelta(days=MOUNT_BREEDING_COOLDOWN_DAYS)
        for m in mounts:
            if m.last_bred_at is not None and (now - m.last_bred_at) < cooldown:
                remaining = cooldown - (now - m.last_bred_at)
                days_left = max(1, remaining.days + (1 if remaining.seconds else 0))
                raise ValueError(
                    f"{m.species.name} is still resting — "
                    f"{days_left} day(s) until it can breed again"
                )

        picked_species = random.choice([mounts[0].species, mounts[1].species])
        picked_potion = random.choice([mounts[0].potion, mounts[1].potion])

        chromatic = False
        if random.random() < CHROMATIC_UPGRADE_CHANCE:
            from apps.pets.models import PotionType
            cosmic = PotionType.objects.filter(slug=CHROMATIC_POTION_SLUG).first()
            if cosmic:
                picked_potion = cosmic
                chromatic = True

        egg_item = ItemDefinition.objects.filter(
            item_type=ItemDefinition.ItemType.EGG,
            pet_species=picked_species,
        ).first()
        if egg_item is None:
            raise ValueError(
                f"No egg item registered for {picked_species.name} — content seed may be incomplete"
            )
        potion_item = ItemDefinition.objects.filter(
            item_type=ItemDefinition.ItemType.POTION,
            potion_type=picked_potion,
        ).first()
        if potion_item is None:
            raise ValueError(
                f"No potion item registered for {picked_potion.name} — content seed may be incomplete"
            )

        for item in (egg_item, potion_item):
            inv, _ = UserInventory.objects.get_or_create(
                user=user, item=item, defaults={"quantity": 0},
            )
            inv.quantity += 1
            inv.save(update_fields=["quantity", "updated_at"])

        for m in mounts:
            m.last_bred_at = now
            m.save(update_fields=["last_bred_at", "updated_at"])

        logger.info(
            "User %s bred mounts %s + %s → %s-%s egg%s",
            user.username, mounts[0].pk, mounts[1].pk,
            picked_species.slug, picked_potion.slug,
            " (chromatic!)" if chromatic else "",
        )

        try:
            from apps.notifications.services import notify, notify_parents
            chrome_tag = " (Cosmic!)" if chromatic else ""
            title = f"Bred a {picked_potion.name} {picked_species.name} egg{chrome_tag}"
            msg = (
                f"{egg_item.name} and {potion_item.name} are in your inventory. "
                "Hatch them to meet your hybrid."
            )
            notify(
                user, title=title, message=msg,
                notification_type="mount_bred",
                link="/bestiary?tab=hatchery",
            )
            notify_parents(
                title=f"{user.display_name or user.username} bred mounts",
                message=msg,
                notification_type="mount_bred",
                about_user=user,
                link="/bestiary?tab=hatchery",
            )
        except Exception:
            logger.exception("Notification hook failed in breed_mounts")

        return {
            "egg_item_id": egg_item.pk,
            "egg_item_name": egg_item.name,
            "egg_item_icon": egg_item.icon,
            "egg_item_sprite_key": egg_item.sprite_key,
            "potion_item_id": potion_item.pk,
            "potion_item_name": potion_item.name,
            "potion_item_icon": potion_item.icon,
            "potion_item_sprite_key": potion_item.sprite_key,
            "picked_species": picked_species.name,
            "picked_species_slug": picked_species.slug,
            "picked_potion": picked_potion.name,
            "picked_potion_slug": picked_potion.slug,
            "chromatic": chromatic,
            "cooldown_days": MOUNT_BREEDING_COOLDOWN_DAYS,
        }

    @staticmethod
    def get_stable(user):
        """Return all pets and mounts for a user, plus collection stats."""
        from django.db.models import Prefetch
        from apps.pets.models import (
            MountExpedition, PetSpecies, PotionType, UserMount, UserPet,
        )

        pets = list(UserPet.objects.filter(user=user).select_related("species", "potion"))
        # Same prefetch as MountsView — keep ``UserMountSerializer``'s
        # active-expedition lookup at O(2 queries) regardless of mount count.
        mounts = list(
            UserMount.objects
            .filter(user=user)
            .select_related("species", "potion")
            .prefetch_related(Prefetch(
                "expeditions",
                queryset=MountExpedition.objects.filter(
                    status=MountExpedition.Status.ACTIVE,
                ).order_by("-started_at"),
                to_attr="prefetched_active_expeditions",
            ))
        )
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
