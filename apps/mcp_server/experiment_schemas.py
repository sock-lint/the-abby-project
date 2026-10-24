"""Bounded saved Progression Lab inputs and explicit evidence result shapes."""
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, model_validator

from .schemas import _Base
from .workbench_schemas import ProgressionReportOut, WorkbenchResult


class ListProgressionExperimentsIn(_Base):
    include_archived: StrictBool = False
    after: UUID | None = None
    limit: StrictInt = Field(default=20, ge=1, le=20)


class ProgressionExperimentIn(_Base):
    experiment_id: UUID


class ProgressionComparisonIn(ProgressionExperimentIn):
    comparison_id: UUID


class ProgressionExperimentWriteIn(_Base):
    request_id: UUID
    name: str = Field(min_length=1, max_length=100)
    hypothesis: str = Field(min_length=1, max_length=2000)
    config: dict[str, Any]
    candidate_daily_coins: StrictInt | None = Field(ge=0, le=100000)
    candidate_policy: Literal[
        "envelope", "commitment100", "expedition_limits", "milestone_gates", "tenure_gates",
    ] = "envelope"
    candidate_expedition_budget: dict[str, Any] = Field(default_factory=dict)
    targets: list[dict[str, Any]] = Field(max_length=6)

    @model_validator(mode="after")
    def bound_inputs(self):
        from apps.rpg.progression import normalize_config
        from apps.rpg.progression.feedback import normalize_targets

        payload = {"config": self.config, "candidate_expedition_budget": self.candidate_expedition_budget,
                   "targets": self.targets}
        if len(json.dumps(payload, allow_nan=False).encode()) > 20000:
            raise ValueError("Experiment assumptions contain at most 20 KB.")
        normalize_config(self.config)
        normalize_targets(self.targets)
        return self


class SaveProgressionExperimentIn(ProgressionExperimentWriteIn, ProgressionExperimentIn):
    revision: StrictInt = Field(ge=1, le=2147483647)


class ProgressionExperimentMutationIn(ProgressionExperimentIn):
    request_id: UUID
    revision: StrictInt = Field(ge=1, le=2147483647)


class RecordProgressionDecisionIn(ProgressionExperimentMutationIn):
    comparison_id: UUID
    outcome: Literal["keep_testing", "revise", "ready_for_design"]
    rationale: str = Field(min_length=1, max_length=2000)
    next_action: str = Field(min_length=1, max_length=2000)
    review_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ProgressionObservationsIn(_Base):
    pass


class ProgressionDecisionOut(WorkbenchResult):
    id: str
    comparison_id: str
    outcome: str
    rationale: str
    next_action: str
    review_on: str
    created_at: str


class ProgressionExperimentSummaryOut(WorkbenchResult):
    is_archived: bool
    id: str
    name: str
    hypothesis: str
    revision: int
    updated_at: str
    latest_decision: ProgressionDecisionOut | None


class ProgressionExperimentListOut(WorkbenchResult):
    schema_version: int
    experiments: list[ProgressionExperimentSummaryOut]
    limits: dict[str, Any]
    feedback: dict[str, Any]
    total: int
    has_more: bool
    next_after: str | None


class ProgressionComparisonSummaryOut(WorkbenchResult):
    id: str
    experiment_revision: int
    created_at: str
    evaluation: dict[str, Any]
    stale: bool
    freshness: Literal["current", "stale", "unavailable"]
    binding: dict[str, Any]


class ProgressionComparisonOut(ProgressionComparisonSummaryOut):
    inputs: dict[str, Any]
    control: ProgressionReportOut
    candidate: ProgressionReportOut


class ProgressionObservationsOut(WorkbenchResult):
    schema_version: int
    status: str
    period: dict[str, Any]
    cohort: dict[str, Any]
    activity: dict[str, Any]
    ledger: dict[str, Any]
    automatic_sources: dict[str, Any]
    policy: dict[str, Any]
    notes: list[str]


class ProgressionObservationOut(WorkbenchResult):
    id: str
    created_at: str
    experiment_revision: int
    status: str
    payload: ProgressionObservationsOut
    binding: dict[str, Any]


class ProgressionExperimentOut(ProgressionExperimentSummaryOut):
    config: dict[str, Any]
    candidate_daily_coins: int | None
    candidate_policy: str
    candidate_expedition_budget: dict[str, Any]
    targets: list[dict[str, Any]]
    comparisons: list[ProgressionComparisonSummaryOut]
    decisions: list[ProgressionDecisionOut]
    observations: list[ProgressionObservationOut]
    observations_redacted: bool
