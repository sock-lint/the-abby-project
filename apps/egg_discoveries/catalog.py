"""Read-only exact supported offers; acceptance freezes these terms once."""
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.utils import timezone

from apps.pets.models import PetIncubation, UserMount, UserPet
from apps.pets.roster import prepared_family
from apps.quests.activity import household_timezone
from apps.rpg.catalog_support import available_pet_pairs, egg_species, item_is_available
from apps.rpg.models import ItemDefinition

from .models import EggDiscovery


RARITIES = ("common", "uncommon", "rare", "epic", "legendary")


def requirements_for(tier):
    rare = tier == "rare"
    return {
        "total_minutes": None if rare else 240,
        "min_minutes_per_type": None if rare else 90,
        "activity_types_required": 2,
        "minutes_per_search_type": 30 if rare else None,
        "minutes_per_search": 60 if rare else None,
        "max_minutes_per_type_per_search": 30 if rare else None,
        "chance_percent": 20 if rare else None,
        "guaranteed_search": 5 if rare else None,
        "required_hatched_species": 2 if rare else 0,
    }


def egg_name(egg):
    # Existing species labels can name a baby stage. A child-facing discovery
    # uses the natural egg identity without revealing any lifecycle artwork.
    if prepared_family(egg.pet_species):
        return egg.slug.removeprefix("meshtint-").removesuffix("-egg").replace("-", " ").title() + " Egg"
    return egg.display_name


def item_receipt(item, quantity, *, name=None):
    return {
        "item_id": item.pk, "item_name": name or item.display_name,
        "item_type": item.item_type, "item_icon": item.icon,
        "item_sprite_key": item.sprite_key, "quantity": quantity,
    }


def _season(key):
    seasons = getattr(settings, "EGG_DISCOVERY_SEASONS", {})
    if not isinstance(seasons, dict):
        return None, "Seasonal availability is not configured correctly."
    if key not in seasons:
        return None, None
    try:
        value = seasons[key]
        starts, ends = date.fromisoformat(value["starts_on"]), date.fromisoformat(value["ends_on"])
        if starts > ends or starts.isoformat() != value["starts_on"] or ends.isoformat() != value["ends_on"]:
            raise ValueError
    except (TypeError, KeyError, ValueError):
        return None, "Seasonal availability is not configured correctly."
    return {"starts_on": starts.isoformat(), "ends_on": ends.isoformat()}, None


def hatched_species_count(user):
    # Evolved pets remain UserPet rows. Completed incubation receipts also
    # retain historical hatches after the corresponding pet was removed.
    species = set(UserPet.objects.filter(user=user).values_list("species_id", flat=True))
    species.update(PetIncubation.objects.filter(user=user, hatched_at__isnull=False).values_list("species_id", flat=True))
    return len(species)


@dataclass
class Offer:
    key: str
    egg: ItemDefinition
    potion: ItemDefinition
    food: ItemDefinition | None
    tier: str
    season: dict | None
    unavailable_reason: str | None

    def public(self):
        return {
            "key": self.key, "name": f"{egg_name(self.egg)} · {self.potion.potion_type.name}",
            "species_slug": self.egg.pet_species.slug, "potion_slug": self.potion.potion_type.slug,
            "tier": self.tier,
            "egg_item": {"id": self.egg.pk, "name": egg_name(self.egg), "icon": self.egg.icon, "sprite_key": self.egg.sprite_key},
            "potion_name": self.potion.potion_type.name,
            "eligible": self.unavailable_reason is None,
            "unavailable_reason": self.unavailable_reason,
            "season": self.season,
            "requirements": requirements_for(self.tier),
        }

    def snapshot(self):
        value = self.public()
        value.pop("eligible")
        value.pop("unavailable_reason")
        return {
            "version": 1, **value,
            "reward_items": [item_receipt(self.egg, 1, name=egg_name(self.egg)), item_receipt(self.potion, 1), item_receipt(self.food, 2)],
            "bindings": {
                "egg_slug": self.egg.slug, "egg_species": self.egg.metadata.get("species"),
                "potion_slug": self.potion.slug, "potion_variant": self.potion.metadata.get("variant"),
            },
        }


def offers_for(user):
    """Project current offers; ``None`` inspects global rollout readiness only."""
    pairs = available_pet_pairs()
    items = list(ItemDefinition.objects.filter(item_type__in=["egg", "potion", "food"]).select_related("pet_species", "potion_type"))
    eggs = [item for item in items if item.item_type == "egg" and item.slug and item.pet_species_id and isinstance(item.metadata, dict)
            and egg_species(item) == item.pet_species and item_is_available(item)]
    potions = [item for item in items if item.item_type == "potion" and item.slug and item.potion_type_id and item.potion_type.slug
               and isinstance(item.metadata, dict) and item_is_available(item)]
    foods = sorted((item for item in items if item.item_type == "food" and item.rarity == "common" and item_is_available(item)),
                   key=lambda item: (item.slug or "", item.pk))
    accepted, owned, pending = set(), set(), set()
    if user is not None:
        accepted = set(EggDiscovery.objects.filter(user=user).values_list("species_id", "potion_type_id"))
        owned = set(UserPet.objects.filter(user=user).values_list("species_id", "potion_id"))
        owned.update(UserMount.objects.filter(user=user).values_list("species_id", "potion_id"))
        pending = set(PetIncubation.objects.filter(user=user, hatched_at__isnull=True).values_list("species_id", "potion_type_id"))
    hatched = hatched_species_count(user) if user is not None else 2
    today = timezone.localdate(timezone=household_timezone(user)) if user is not None else timezone.localdate()
    result = []
    for egg in eggs:
        for potion in potions:
            pair = (egg.pet_species_id, potion.potion_type_id)
            if pair not in pairs or egg.pet_species.rarity not in RARITIES or potion.potion_type.rarity not in RARITIES:
                continue
            tier = "rare" if max(RARITIES.index(egg.pet_species.rarity), RARITIES.index(potion.potion_type.rarity)) >= 2 else "ordinary"
            key = f"{egg.slug}:{potion.potion_type.slug}"
            season, reason = _season(key)
            food = next((item for item in foods if item.food_species_id == egg.pet_species_id), foods[0] if foods else None)
            if not reason and pair in accepted:
                reason = "This discovery is already saved in your collection."
            if not reason and pair in owned:
                reason = "You have already hatched this companion."
            if not reason and pair in pending:
                reason = "This companion is already in your Hatchery."
            if not reason and food is None:
                reason = "The hatching supplies for this discovery are unavailable."
            if not reason and tier == "rare" and hatched < 2:
                reason = "Hatch two different companions to unlock rare discoveries."
            if not reason and season and not (season["starts_on"] <= today.isoformat() <= season["ends_on"]):
                reason = "Choose this discovery during its seasonal start window."
            result.append(Offer(key, egg, potion, food, tier, season, reason))
    return sorted(result, key=lambda offer: (offer.tier == "rare", offer.key))
