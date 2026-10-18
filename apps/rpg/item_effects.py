"""Read-only item explanations shared with authoritative food calculations."""

FOOD_GROWTH_BY_RARITY = {"common": 5, "uncommon": 8, "rare": 10, "epic": 12, "legendary": 15}
PREFERRED_FOOD_BONUS = 10
MAX_AUTHORED_FOOD_GROWTH = 30


def food_base_growth(item):
    """Rarity establishes a floor; valid authored food can be more nourishing.

    Legacy/malformed metadata never causes an enormous, negative or bool feed.
    Common treats retain at least the original five-point neutral effect.
    """
    baseline = FOOD_GROWTH_BY_RARITY.get(item.rarity, 5)
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    authored = metadata.get("growth")
    if type(authored) is int and 1 <= authored <= MAX_AUTHORED_FOOD_GROWTH:
        return max(baseline, authored)
    return baseline


def effect_summary(item):
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    if item.item_type == "food":
        return f"Adds {food_base_growth(item)} growth, plus {PREFERRED_FOOD_BONUS} for a preferred food. Growth Tonic doubles the total."
    if item.item_type == "coin_pouch":
        coins = metadata.get("coins") or item.coin_value or 0
        if type(coins) is int and coins >= 0:
            return f"Open to collect {coins} coins."
    if item.item_type == "cosmetic_theme":
        return "Choose this color theme in Settings."
    if item.item_type == "cosmetic_pet_accessory":
        return item.description or "A saved pet accessory."
    if item.item_type.startswith("cosmetic_"):
        return "Equip this collectible from your Profile."
    if item.item_type == "egg":
        return "Combine with a compatible potion in Hatching to meet this companion."
    if item.item_type == "potion":
        return "Combine with a compatible egg in Hatching."
    return item.description or ""
