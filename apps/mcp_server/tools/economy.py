"""Server-owned rules, anonymous projections, and same-family ledger audits."""
from typing import Any

from ..context import get_current_user, resolve_target_user
from ..economy import coin_ledger_page, economy_audit, economy_rules, preview_scenarios
from ..economy_schemas import (
    GetEconomyAuditIn, GetEconomyRulesIn, ListCoinLedgerIn, PreviewEconomyScenarioIn,
)
from ..errors import safe_tool
from ..server import tool


@tool()
@safe_tool
def get_economy_rules(params: GetEconomyRulesIn) -> dict[str, Any]:
    """Read authoritative global reward settings, caps, boosts and calculation references; no family records."""
    get_current_user()
    return economy_rules()


@tool()
@safe_tool
def preview_economy_scenario(params: PreviewEconomyScenarioIn) -> dict[str, Any]:
    """Compare up to four anonymous 31-day plans using explicit assumptions and current eligible drop pools.

    Reading, movement, creations, supplied approved chore rewards and explicit
    one-off project/milestone/tracked-work/conditional goal reward assumptions.
    Results are projections, never awards or a prediction of all downstream bonuses.
    Reads global catalog eligibility; never selects a user, invokes a grant or rolls randomness.
    """
    get_current_user()
    return preview_scenarios(params.scenarios)


@tool()
@safe_tool
def list_coin_ledger(params: ListCoinLedgerIn) -> dict[str, Any]:
    """Read persisted Coin amounts through a signed cursor, scoped to self or an authorized same-family user.

    Dates use the target family's current timezone. Repeat filters and user_id
    with next_cursor; new higher-ID rows are excluded from that page sequence.
    Free-text descriptions are omitted to keep this accounting view bounded to
    amounts, typed reasons and receipt links. No ledger or family state changes.
    """
    target = resolve_target_user(get_current_user(), params.user_id)
    return coin_ledger_page(target, params)


@tool()
@safe_tool
def get_economy_audit(params: GetEconomyAuditIn) -> dict[str, Any]:
    """Audit a bounded family-local period from actual CoinLedger amounts and typed receipts.

    Defaults to 30 inclusive days, maximum 366. Refunds, exchanges and mixed
    adjustments are separated from identified earn reasons. Receipt subtotals
    overlap the ledger and must not be added to it. Never sums activity-log
    deltas, estimates missing historic awards or changes rewards.
    """
    target = resolve_target_user(get_current_user(), params.user_id)
    return economy_audit(target, params.since, params.until)
