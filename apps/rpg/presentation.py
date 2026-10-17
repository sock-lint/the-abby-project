"""Current UI labels without changing saved catalog or artwork identities."""
from functools import lru_cache
import json
from pathlib import Path


THEME_PRESENTATION_PATH = Path(__file__).resolve().parents[2] / "shared/catalog/theme-presentation.json"


@lru_cache(maxsize=1)
def theme_presentation():
    return json.loads(THEME_PRESENTATION_PATH.read_text(encoding="utf-8"))


def item_display_name(item):
    if item.item_type == "cosmetic_theme" and isinstance(item.metadata, dict):
        key = item.metadata.get("theme")
        if isinstance(key, str):
            presentation = theme_presentation()
            resolved = presentation["aliases"].get(key, key)
            return presentation["names"].get(resolved, item.name)
    return item.name
