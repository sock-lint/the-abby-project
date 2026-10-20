"""Validated public result fields, preserving additional existing serializer fields.

These models describe wire results, not ORM objects. Dates and monetary values
retain their existing string representation; newly documented fields do not
change the saved business response or remove serializer extensions.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


class Result(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class ProjectResult(Result):
    id: int
    title: str
    description: str
    status: str
    assigned_to: dict[str, Any] | None
    created_at: str


class PaymentResult(Result):
    id: int
    user: int
    amount: str
    entry_type: str
    description: str
    created_at: str
    created_by: int | None


class HistoryPage(Result):
    total: int
    has_more: bool
    next_cursor: str | None


class ProjectPage(HistoryPage):
    projects: list[ProjectResult]
    count: int


class PaymentPage(HistoryPage):
    entries: list[PaymentResult]


class MovementResult(Result):
    id: int
    user: int
    movement_type: int
    duration_minutes: int
    intensity: str
    distance: str | None
    distance_meters: str | None
    distance_unit: str
    client_request_id: str | None
    challenge_receipts: list[dict[str, Any]]
    xp_awarded: int
    occurred_on: str
    created_at: str


class RedemptionResult(Result):
    id: int
    user: int
    reward: dict[str, Any]
    status: str
    coin_cost_snapshot: int
    requested_at: str
    decided_at: str | None


class CatalogPage(Result):
    section: str
    total: int
    after: int
    next_after: int | None
    results: list[dict[str, Any]]


OUTPUT_MODELS = {
    "list_projects": ProjectPage,
    "create_project": ProjectResult,
    "get_project": ProjectResult,
    "list_payment_ledger": PaymentPage,
    "adjust_payment": PaymentResult,
    "record_payout": PaymentResult,
    "log_movement_session": MovementResult,
    "get_movement_session": MovementResult,
    "request_redemption": RedemptionResult,
    "read_rpg_catalog": CatalogPage,
}
