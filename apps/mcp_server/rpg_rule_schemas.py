"""Global installed mechanics and bounded definition-reference explanations."""
from pydantic import Field

from .catalog_schemas import CatalogSection
from .schemas import _Base


class GetRpgRulesIn(_Base):
    pass


class ExplainCatalogEntryIn(_Base):
    section: CatalogSection
    object_id: int = Field(ge=1, strict=True)
    limit: int = Field(default=20, ge=1, le=50)


class RpgRulesResult(_Base):
    schema_version: int
    fingerprint: str
    economy: dict
    food_growth: dict
    companions: dict
    expeditions: dict
    consumable_effects: list[str]
    badge_criteria: dict[str, list[str]]
    authoring: dict[str, list[str]]


class CatalogExplanationResult(_Base):
    section: str
    entry: dict
    findings: list[dict]
    references: list[dict]
    references_truncated: bool
    scope: str
