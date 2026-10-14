"""Base-avatar appearance and shared equipment are free presentation choices.

Registered bindings determine compatibility. Pack provenance never establishes
fit, ownership, rewards or public delivery approval.
"""
from copy import deepcopy


DEFAULT_AVATAR_ID = "female-archer"
SHARED_ACCESSORY_SLOTS = [
    {"id": "headwear", "label": "Headwear"},
    {"id": "face_accessory", "label": "Face accessory"},
    {"id": "left_hand", "label": "Left hand"},
    {"id": "right_hand", "label": "Right hand"},
    {"id": "back", "label": "Back accessory"},
]
SHARED_ACCESSORIES = {
    item_id: {"label": label, "source_pack": "meshtint-female-archer-01"}
    for item_id, label in [
        ("crown-eve", "Eve crown"), ("hood-mystical", "Mystical hood"),
        ("mask-undercover", "Undercover mask"),
        ("bow-greenhorn", "Greenhorn bow"), ("bow-vines", "Vines bow"), ("bow-myth", "Myth bow"),
        ("quiver-angel", "Angel quiver"), ("quiver-rook", "Rook quiver"), ("quiver-tale", "Tale quiver"),
    ]
}


def _field(key, label, choices):
    return {"key": key, "label": label, "choices": [{"value": value, "label": name} for value, name in choices]}


# Only the prepared Archer is offered. An eventual base can bind the SAME
# shared item IDs to its own reviewed joints/socket transforms and hair policy.
# Actual placement remains its renderer adapter's supplied-art responsibility.
AVATAR_DEFINITIONS = {
    DEFAULT_AVATAR_ID: {
        "id": DEFAULT_AVATAR_ID, "label": "Female Archer", "renderer_adapter": "female-archer",
        "defaults": {
            "appearance": {
                "hair_style": "hair-01", "hair_color": "dark", "skin_tone": "fair", "outfit": "nature",
                "outfit_style": "archer-01", "face_style": "face-01", "head_style": "head-02",
            },
            "accessories": {slot["id"]: "none" for slot in SHARED_ACCESSORY_SLOTS},
        },
        "groups": [
            {"id": "identity", "label": "Appearance", "fields": [
                _field("outfit_style", "Outfit", [("archer-01", "Outfit 1"), ("archer-02", "Outfit 2"), ("archer-03", "Outfit 3")]),
                _field("hair_style", "Hairstyle", [("hair-01", "Swept"), ("hair-02", "Bob"), ("hair-03", "Ponytail"), ("hair-04", "Side part")]),
                _field("hair_color", "Hair color", [("light", "Light"), ("dark", "Dark"), ("brown", "Brown"), ("orange", "Orange"), ("grey", "Grey")]),
                _field("face_style", "Face", [("face-01", "Face 1"), ("face-02", "Face 2"), ("face-03", "Face 3")]),
                _field("head_style", "Ears", [("head-01", "Rounded"), ("head-02", "Pointed")]),
                _field("skin_tone", "Skin tone", [("fair", "Fair"), ("tan", "Tan")]),
                _field("outfit", "Palette", [("aqua", "Aqua"), ("nature", "Nature"), ("fire", "Fire"), ("dark", "Dark")]),
            ]},
            {"id": "wardrobe", "label": "Accessories", "fields": [
                {"key": slot["id"], "label": slot["label"], "accessory_slot": slot["id"]}
                for slot in SHARED_ACCESSORY_SLOTS
            ]},
        ],
        "accessory_bindings": {
            "headwear": {"item_ids": ["crown-eve", "hood-mystical"], "attachment": "RigHead", "legacy_preference_key": "headwear_style"},
            "face_accessory": {"item_ids": ["mask-undercover"], "attachment": "RigHead", "legacy_preference_key": "mask_style"},
            "left_hand": {"item_ids": ["bow-greenhorn", "bow-vines", "bow-myth"], "attachment": "RigLPalm", "legacy_preference_key": "bow_style"},
            "right_hand": {"item_ids": [], "attachment": None, "legacy_preference_key": None},
            "back": {"item_ids": ["quiver-angel", "quiver-rook", "quiver-tale"], "attachment": "RigRibcage", "legacy_preference_key": "quiver_style"},
        },
        "presets": [
            {"id": "aqua", "label": "Aqua", "appearance": {"outfit": "aqua"}, "accessories": {
                "headwear": "hood-mystical", "face_accessory": "none", "left_hand": "bow-vines", "back": "quiver-angel",
            }},
            {"id": "nature", "label": "Nature", "appearance": {"outfit": "nature"}, "accessories": {
                "headwear": "none", "face_accessory": "mask-undercover", "left_hand": "bow-greenhorn", "back": "quiver-rook",
            }},
            {"id": "fire", "label": "Fire", "appearance": {"outfit": "fire"}, "accessories": {
                "headwear": "crown-eve", "face_accessory": "none", "left_hand": "bow-myth", "back": "quiver-tale",
            }},
            {"id": "dark", "label": "Dark", "appearance": {"outfit": "dark"}, "accessories": {
                "headwear": "hood-mystical", "face_accessory": "mask-undercover", "left_hand": "bow-myth", "back": "quiver-tale",
            }},
        ],
    },
}


def avatar_catalog(definitions=None, *, default_avatar_id=DEFAULT_AVATAR_ID, accessories=None):
    """Return ordered metadata without reading profiles or earned ownership."""
    definitions = AVATAR_DEFINITIONS if definitions is None else definitions
    accessories = SHARED_ACCESSORIES if accessories is None else accessories
    entries = deepcopy(list(definitions.values()))
    for definition in entries:
        for group in definition["groups"]:
            for field in group["fields"]:
                slot = field.get("accessory_slot")
                if slot is not None:
                    item_ids = definition["accessory_bindings"].get(slot, {}).get("item_ids", [])
                    if any(item_id not in accessories for item_id in item_ids):
                        raise ValueError("Accessory bindings must reference registered shared items.")
                    field["choices"] = [{"value": "none", "label": "None"}, *[
                        {"value": item_id, "accessory_id": item_id} for item_id in item_ids
                    ]]
    return deepcopy({
        "schema_version": 1, "default_avatar_id": default_avatar_id,
        "accessory_slots": SHARED_ACCESSORY_SLOTS, "accessories": accessories, "avatars": entries,
    })


def avatar_options(avatar_id, *, definitions=None):
    """Each base defines its appearance keys; there are no universal body fields."""
    definitions = AVATAR_DEFINITIONS if definitions is None else definitions
    return {
        field["key"]: tuple(choice["value"] for choice in field["choices"])
        for group in definitions[avatar_id]["groups"] for field in group["fields"]
        if "accessory_slot" not in field
    }


# Preserve the existing Archer-only flat request and its allowed-value order.
AVATAR_OPTIONS = {
    **avatar_options(DEFAULT_AVATAR_ID),
    **{binding["legacy_preference_key"]: ("none", *binding["item_ids"])
       for binding in AVATAR_DEFINITIONS[DEFAULT_AVATAR_ID]["accessory_bindings"].values()
       if binding["legacy_preference_key"] is not None},
}
AVATAR_DEFAULTS = {
    **AVATAR_DEFINITIONS[DEFAULT_AVATAR_ID]["defaults"]["appearance"],
    **{binding["legacy_preference_key"]: "none"
       for binding in AVATAR_DEFINITIONS[DEFAULT_AVATAR_ID]["accessory_bindings"].values()
       if binding["legacy_preference_key"] is not None},
}


def avatar_appearance(saved):
    saved = saved if isinstance(saved, dict) else {}
    return {key: saved.get(key) if saved.get(key) in choices else AVATAR_DEFAULTS[key]
            for key, choices in AVATAR_OPTIONS.items()}


def configuration_from_preferences(preferences):
    selected = avatar_appearance(preferences)
    definition = AVATAR_DEFINITIONS[DEFAULT_AVATAR_ID]
    return {
        "avatar_id": DEFAULT_AVATAR_ID,
        "appearance": {key: selected[key] for key in definition["defaults"]["appearance"]},
        "accessories": {
            slot["id"]: selected.get(definition["accessory_bindings"].get(slot["id"], {}).get("legacy_preference_key"), "none")
            for slot in SHARED_ACCESSORY_SLOTS
        },
    }


def saved_avatar_configuration(configuration, preferences):
    # {} is the migration's unsaved sentinel. Nonempty/unknown saved bodies and
    # gear remain visible as saved state, even if a prepared adapter is missing.
    return configuration_from_preferences(preferences) if configuration == {} else deepcopy(configuration)


def legacy_preferences_from_configuration(configuration):
    if configuration["avatar_id"] != DEFAULT_AVATAR_ID:
        return None
    return {
        **configuration["appearance"],
        **{binding["legacy_preference_key"]: configuration["accessories"][slot]
           for slot, binding in AVATAR_DEFINITIONS[DEFAULT_AVATAR_ID]["accessory_bindings"].items()
           if binding["legacy_preference_key"] is not None},
    }


class AvatarConfigurationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Unsupported avatar configuration.")


def normalize_avatar_configuration(value):
    """Strict full replacement against base controls and explicit fitted IDs."""
    if not isinstance(value, dict):
        raise AvatarConfigurationError(["Avatar configuration must be an object."])
    unknown = set(value) - {"avatar_id", "appearance", "accessories"}
    if unknown:
        raise AvatarConfigurationError({key: ["This configuration field is not supported."] for key in sorted(unknown)})
    avatar_id = value.get("avatar_id")
    if not isinstance(avatar_id, str) or avatar_id not in AVATAR_DEFINITIONS:
        raise AvatarConfigurationError({"avatar_id": ["Choose a supported avatar."]})
    definition = AVATAR_DEFINITIONS[avatar_id]
    appearance = value.get("appearance", {})
    accessories = value.get("accessories", {})
    errors = {}
    if not isinstance(appearance, dict):
        errors["appearance"] = ["Appearance choices must be an object."]
    else:
        options = avatar_options(avatar_id)
        invalid = {key: ["Choose a supported appearance option."] for key, selected in appearance.items()
                   if key not in options or not isinstance(selected, str) or selected not in options[key]}
        if invalid:
            errors["appearance"] = invalid
    if not isinstance(accessories, dict):
        errors["accessories"] = ["Accessory choices must be an object."]
    else:
        slots = {slot["id"] for slot in SHARED_ACCESSORY_SLOTS}
        invalid = {}
        for slot, item_id in accessories.items():
            binding = definition["accessory_bindings"].get(slot, {})
            if slot not in slots or not isinstance(item_id, str) or (item_id != "none" and (
                item_id not in SHARED_ACCESSORIES or item_id not in binding.get("item_ids", []) or not binding.get("attachment")
            )):
                invalid[slot] = ["Choose None or an item fitted to this avatar slot."]
        if invalid:
            errors["accessories"] = invalid
    if errors:
        raise AvatarConfigurationError(errors)
    return {"avatar_id": avatar_id, "appearance": {**definition["defaults"]["appearance"], **appearance},
            "accessories": {slot["id"]: accessories.get(slot["id"], definition["defaults"]["accessories"].get(slot["id"], "none"))
                            for slot in SHARED_ACCESSORY_SLOTS}}
