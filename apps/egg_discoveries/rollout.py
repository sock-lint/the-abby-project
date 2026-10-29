"""Read-only readiness of the installed catalog, never deployment authority."""
from django.conf import settings

from .catalog import offers_for
from .policy import discovery_enabled


def readiness():
    offers = offers_for(None)
    ordinary = {offer.egg.pet_species_id for offer in offers if offer.tier == "ordinary" and not offer.unavailable_reason}
    problems = []
    if len(ordinary) < 2:
        problems.append("At least two ordinary species must be startable so a new child can unlock rare discoveries.")
    problems.extend(f"{offer.key}: {offer.unavailable_reason}" for offer in offers
                    if offer.unavailable_reason and offer.unavailable_reason != "Choose this discovery during its seasonal start window.")
    seasons = getattr(settings, "EGG_DISCOVERY_SEASONS", {})
    if not isinstance(seasons, dict):
        problems.append("Seasonal availability must be an exact-offer mapping.")
    else:
        keys = {offer.key for offer in offers}
        problems.extend(f"Seasonal offer is not in the supported catalog: {key}" for key in seasons if key not in keys)
    return {
        "catalog_ready": not problems,
        "enabled": discovery_enabled(),
        "ordinary_species_startable": len(ordinary),
        "ordinary_pairs": sum(offer.tier == "ordinary" for offer in offers),
        "rare_pairs": sum(offer.tier == "rare" for offer in offers),
        "problems": problems,
        "scope": "Global catalog only. This is not a deployment or mixed-writer safety check.",
    }
