"""Global RPG authoring inputs and structural audit, separate from player access."""
from typing import Any

from ..catalog import audit_catalog_rows, catalog_page, catalog_row
from ..catalog_schemas import CatalogPageIn
from ..context import get_current_user
from ..errors import safe_tool
from ..server import tool
from ..shapes import to_plain


@tool()
@safe_tool
def read_rpg_catalog(params: CatalogPageIn) -> dict[str, Any]:
    """Read one global section in primary-key order with a stable after cursor.

    Includes authored rules, exact badge criteria, skill prerequisites, quest
    skill/reward wiring and effective acquisition availability. Unsupported
    reward items remain visible for audit. Quest definitions are system-only;
    private family templates, goals, journals and player state are excluded.
    total is the full section count, not merely this page's count.
    """
    get_current_user()
    rows, page = catalog_page(params)
    return to_plain({**page, "results": [catalog_row(params.section, row) for row in rows]})


@tool()
@safe_tool
def audit_rpg_catalog(params: CatalogPageIn) -> dict[str, Any]:
    """Inspect one bounded catalog page without modifying rules or player state.

    Reports unsupported item promises, invalid criteria/triggers, unreachable
    new-player collectible prerequisites, missing global references, skill
    cycles and XP without a target. Reachability honors current asset policy;
    saved ownership may still satisfy retained promises. This is a structural
    audit, not a balance recommendation or a reward simulation. Skill graphs
    are capped at 5,000 edges and explicitly report an incomplete graph.
    """
    get_current_user()
    rows, page = catalog_page(params)
    findings, incomplete = audit_catalog_rows(params.section, rows)
    return {**page, "checked": len(rows), "findings": findings, "incomplete": incomplete}
