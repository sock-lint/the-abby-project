"""Shared constants for the Creations app.

The creative-subset list is the authoritative allow-list of skill-tree
categories a child may tag a Creation with. Keep this list in sync with
the grouping rendered by ``CreationLogModal`` on the frontend.
"""

# Skill-tree categories that accept Creation tags. A child-submitted
# ``primary_skill_id`` must belong to one of these categories.
CREATIVE_CATEGORY_NAMES = [
    "Art & Crafts",
    "Making & Fabrication",
    "Music",
    "Cooking",
    "Creative Writing",
    "Sewing & Textiles",
    "Woodworking",
]
