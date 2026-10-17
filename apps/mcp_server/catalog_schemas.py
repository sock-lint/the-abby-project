"""Cursor-bounded reads of global RPG configuration; never player records."""
from typing import Literal

from pydantic import Field

from .schemas import _Base


class CatalogPageIn(_Base):
    section: Literal[
        "categories", "subjects", "skills", "badges", "quests", "items",
        "drops", "pet_species", "potion_types",
    ]
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)
