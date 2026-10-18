"""Acquisition rarity is separate from potion artwork and lifecycle stage."""

RARITY_CHOICES = [(key, key.title()) for key in ("common", "uncommon", "rare", "epic", "legendary")]
RARITY_ORDER = {key: index for index, (key, _label) in enumerate(RARITY_CHOICES)}


def companion_rarity(species, potion=None):
    """Keep a saved higher-tier potion while giving Base companions their species tier.

    Callers already load species and potion for their normal response. Reading
    scalar fields adds no database lookup and growth never changes this tier.
    """
    values = (getattr(species, "rarity", "common"), getattr(potion, "rarity", "common"))
    return max((value for value in values if value in RARITY_ORDER), key=RARITY_ORDER.get, default="common")
