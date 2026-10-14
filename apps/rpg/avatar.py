"""Appearance options supported by the recorded owned Female Archer pack."""
AVATAR_OPTIONS = {
    "hair_style": ("hair-01", "hair-02", "hair-03", "hair-04"),
    "hair_color": ("light", "dark", "brown", "orange", "grey"),
    "skin_tone": ("fair", "tan"),
    "outfit": ("aqua", "nature", "fire", "dark"),
    "outfit_style": ("archer-01", "archer-02", "archer-03"),
    "face_style": ("face-01", "face-02", "face-03"),
    "head_style": ("head-01", "head-02"),
    "headwear_style": ("none", "crown-eve", "hood-mystical"),
    "mask_style": ("none", "mask-undercover"),
    "bow_style": ("none", "bow-greenhorn", "bow-vines", "bow-myth"),
    "quiver_style": ("none", "quiver-angel", "quiver-rook", "quiver-tale"),
}
AVATAR_DEFAULTS = {
    "hair_style": "hair-01", "hair_color": "dark",
    "skin_tone": "fair", "outfit": "nature", "outfit_style": "archer-01", "face_style": "face-01",
    "head_style": "head-02",
    "headwear_style": "none", "mask_style": "none", "bow_style": "none", "quiver_style": "none",
}


def avatar_appearance(saved):
    saved = saved if isinstance(saved, dict) else {}
    return {
        key: saved.get(key) if saved.get(key) in choices else AVATAR_DEFAULTS[key]
        for key, choices in AVATAR_OPTIONS.items()
    }
