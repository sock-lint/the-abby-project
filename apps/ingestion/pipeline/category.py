"""Map free-text (title/description/source category) to an existing SkillCategory."""
from __future__ import annotations

# keyword -> target SkillCategory.name. Matched case-insensitively against a
# blob of title + description + source category hint. First category with the
# highest keyword-hit count wins; ties broken by table order.
KEYWORD_MAP: dict[str, list[str]] = {
    "Sewing": ["sew", "stitch", "fabric", "needle", "thread", "quilt", "seam"],
    "Knitting": ["knit", "yarn", "crochet", "loom", "skein"],
    "Woodworking": ["wood", "sand", "saw", "plank", "plywood", "lumber", "drill", "router"],
    "Cooking": ["recipe", "bake", "cook", "oven", "ingredients", "dough", "flour"],
    "Electronics": ["solder", "arduino", "circuit", "resistor", "led", "breadboard", "microcontroller"],
    "Art": ["paint", "draw", "sketch", "canvas", "acrylic", "watercolor"],
    "Crafts": ["glue", "paper", "cardboard", "craft", "origami"],
    "Gardening": ["plant", "garden", "soil", "seed", "sprout", "compost"],
    "3D Printing": ["print", "filament", "pla", "slicer", "extruder"],
    "Robotics": ["robot", "servo", "motor", "chassis", "gearbox"],
}


def guess_category(*text_parts: str | None) -> str | None:
    """Return the best-matching category name, or None if nothing matches.

    Only returns names that exist in :class:`SkillCategory`; caller still must
    resolve to the actual row.
    """
    blob = " ".join(p.lower() for p in text_parts if p)
    if not blob:
        return None

    best_name: str | None = None
    best_score = 0
    for name, keywords in KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in blob)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score > 0 else None


def resolve_category_id(name: str | None) -> int | None:
    """Resolve a category name to a SkillCategory PK, case-insensitively."""
    if not name:
        return None
    # Imported lazily to avoid app-registry issues at import time.
    from apps.projects.models import SkillCategory

    match = SkillCategory.objects.filter(name__iexact=name).first()
    return match.id if match else None
