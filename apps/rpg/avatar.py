"""Appearance options supported by the recorded owned Female Archer pack."""
AVATAR_OPTIONS = {
    "hair_style": ("hair-01", "hair-02", "hair-03", "hair-04"),
    "hair_color": ("light", "dark"),
    "skin_tone": ("fair", "tan"),
    "outfit": ("aqua", "nature", "fire", "dark"),
}
AVATAR_DEFAULTS = {
    "hair_style": "hair-01", "hair_color": "dark",
    "skin_tone": "fair", "outfit": "nature",
}


def avatar_appearance(saved):
    saved = saved if isinstance(saved, dict) else {}
    return {
        key: saved.get(key) if saved.get(key) in choices else AVATAR_DEFAULTS[key]
        for key, choices in AVATAR_OPTIONS.items()
    }
