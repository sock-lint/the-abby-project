"""Read-only card artwork for exact existing cosmetic identities.

These bindings change presentation only. Inventory and CosmeticService retain
ownership, acquisition and equip authority; metadata cannot select extra art.
"""


_CARD_STYLE_BINDINGS = {
    "frame-robin-hood": ("Ranger's Cap Frame", "card-front-nature"),
    "frame-scholar": ("Scholar Frame", "card-front-light"),
}


def card_style_metadata(item):
    """Copy metadata and project an allowlisted card ID without stored writes."""
    if not isinstance(item.metadata, dict):
        return item.metadata
    metadata = {key: value for key, value in item.metadata.items() if key != "card_asset_id"}
    binding = _CARD_STYLE_BINDINGS.get(item.slug)
    if item.item_type == "cosmetic_frame" and binding and item.name == binding[0]:
        metadata["card_asset_id"] = binding[1]
    return metadata
