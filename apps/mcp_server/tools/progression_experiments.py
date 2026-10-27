"""Private saved design evidence, separate from publishing or live rewards."""
from contextlib import nullcontext
import math
from types import SimpleNamespace

from apps.rpg.experiment_views import ComparisonThrottle
from apps.rpg.models import ProgressionComparison, ProgressionExperiment
from apps.rpg.progression import experiments
from apps.rpg.progression.observations import economy_observations

from ..context import get_current_scopes, require_scope, require_staff_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..experiment_schemas import (
    ListProgressionExperimentsIn, ProgressionComparisonIn, ProgressionComparisonOut,
    ProgressionExperimentIn, ProgressionExperimentListOut, ProgressionExperimentMutationIn,
    ProgressionExperimentOut, ProgressionExperimentWriteIn, ProgressionObservationsIn,
    ProgressionObservationsOut, RecordProgressionDecisionIn, SaveProgressionExperimentIn,
)
from ..models import MCPExperimentMutationReceipt
from ..retries import authorized_household
from ..server import tool
from ..shapes import to_plain


def _actor():
    actor = require_staff_parent()
    if not actor.is_active:
        raise MCPPermissionDenied("Progression experiments require an active staff parent.")
    return actor


def _call(function, *args, **kwargs):
    return to_plain(_native(function, *args, **kwargs))


def _native(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except experiments.ExperimentNotFound as error:
        raise MCPNotFoundError(str(error)) from error
    except experiments.ExperimentConflict as error:
        raise MCPValidationError(str(error), code="progression_experiment_conflict") from error
    except experiments.ExperimentUnavailable as error:
        raise MCPValidationError(str(error), code="progression_catalog_unavailable", retryable=True) from error


def _include_observations():
    return "mcp:read" in get_current_scopes()


def _detail(actor, experiment_id):
    include = _include_observations()
    result = _call(experiments.get_experiment, actor, experiment_id, include_observations=include)
    # Keep the grant boundary explicit even when no checkpoint exists yet.
    return {**result, "observations_redacted": not include}


def _serialize(actor, experiment, result_kind, result_id):
    if result_kind == "comparison":
        return _call(experiments.get_comparison, actor, experiment.pk, result_id)
    return _detail(actor, experiment.pk)


def _freshness_snapshot(actor, experiment_id, *, for_decision=False):
    """Build today's catalog binding before household locks when a reply needs it.

    Ordinary replies without saved comparisons skip freshness. A decision
    always prepares its source-bound snapshot before entering household locks.
    """
    if not for_decision and (experiment_id is None or not ProgressionComparison.objects.filter(
        experiment_id=experiment_id, experiment__actor=actor, experiment__family_id=actor.family_id,
    ).exists()):
        return nullcontext()
    return experiments.request_catalog_binding(for_decision=for_decision)


def _mutate(params, operation, create):
    from ..experiment_retries import experiment_mutation_once

    actor = _actor()
    # A create carries no experiment ID; its replay reports the saved one.
    experiment_id = getattr(params, "experiment_id", None) or MCPExperimentMutationReceipt.objects.filter(
        actor=actor, operation=operation, request_id=params.request_id,
    ).values_list("experiment_id", flat=True).first()
    with _freshness_snapshot(actor, experiment_id, for_decision=operation == "record_progression_decision"):
        return experiment_mutation_once(
            actor=actor, operation=operation, request_id=params.request_id,
            payload=params.model_dump(mode="json", exclude={"request_id"}, exclude_unset=True),
            create=create, serialize=_serialize,
        )


def _evidence(params, operation, *, precheck, prepare, persist):
    from ..experiment_retries import experiment_evidence_once

    return experiment_evidence_once(
        actor=_actor(), operation=operation, request_id=params.request_id,
        payload=params.model_dump(mode="json", exclude={"request_id"}, exclude_unset=True),
        precheck=precheck, prepare=prepare, persist=persist, serialize=_serialize,
    )


def _saved(actor, experiment_id):
    # Native services already validate author/family/revision before writing.
    # Resolve only their resulting identity for the retry receipt.
    return ProgressionExperiment.objects.get(pk=experiment_id, actor=actor, family_id=actor.family_id)


def _comparison_quota(actor):
    throttle = ComparisonThrottle()
    if not throttle.allow_request(SimpleNamespace(user=actor), None):
        seconds = max(1, math.ceil(throttle.wait() or 60))
        raise MCPValidationError(
            f"Comparison rate limit reached. Try again in {seconds} seconds.",
            code="rate_limited", retryable=True,
        )


@tool()
@safe_tool
def list_progression_experiments(params: ListProgressionExperimentsIn) -> ProgressionExperimentListOut:
    """List this staff parent's private saved hypotheses, in bounded UUID order.

    Follow next_after with after. Active entries appear by default; use
    include_archived for retained history. Summaries never contain observations.
    """
    actor = _actor()
    with authorized_household(actor, actor) as (fresh_actor, _):
        return _call(experiments.list_experiments, fresh_actor, include_archived=params.include_archived,
                     after=params.after, limit=params.limit)


@tool()
@safe_tool
def get_progression_experiment(params: ProgressionExperimentIn) -> ProgressionExperimentOut:
    """Read saved assumptions, comparison summaries and append-only decisions.

    Household checkpoints appear only with an additional mcp:read grant;
    observations_redacted explicitly reports that boundary. Historical evidence
    remains readable when today's catalog is unavailable.
    """
    actor = _actor()
    with _freshness_snapshot(actor, params.experiment_id), authorized_household(actor, actor) as (fresh_actor, _):
        return _detail(fresh_actor, params.experiment_id)


@tool()
@safe_tool
def create_progression_experiment(params: ProgressionExperimentWriteIn) -> ProgressionExperimentOut:
    """Save a private hypothesis and bounded anonymous control/candidate recipe.

    Reuse request_id and identical arguments after an uncertain response. A
    retry reads the same notebook entry's current saved state. Assumptions and
    targets never publish catalog content or change live rewards.
    """
    def create(actor):
        result = _call(experiments.create_experiment, actor, params.model_dump(
            exclude={"request_id"}, exclude_unset=True,
        ), include_observations=False)
        experiment = _saved(actor, result["id"])
        return experiment, "experiment", experiment.pk

    return _mutate(params, "create_progression_experiment", create)


@tool()
@safe_tool
def save_progression_experiment(params: SaveProgressionExperimentIn) -> ProgressionExperimentOut:
    """Revise saved assumptions with the current revision and a stable request_id.

    Revisions retain historical comparisons and mark older evidence stale.
    Identical UUID retries reread current saved state without another revision;
    changed arguments conflict. Omitted policy fields preserve existing choices.
    """
    def create(actor):
        result = _call(experiments.save_experiment, actor, params.experiment_id, params.revision,
                       params.model_dump(exclude={"request_id", "experiment_id", "revision"}, exclude_unset=True),
                       include_observations=False)
        experiment = _saved(actor, result["id"])
        return experiment, "experiment", experiment.pk

    return _mutate(params, "save_progression_experiment", create)


@tool()
@safe_tool
def compare_progression_experiment(params: ProgressionExperimentMutationIn) -> ProgressionComparisonOut:
    """Save immutable server-generated paired evidence for one saved revision.

    Both arms share seeds and one global catalog. The native five-per-minute
    comparison budget applies across REST and MCP. Reuse request_id for a retry;
    an existing comparison is read without rerunning or spending another quota.
    """
    def precheck(actor):
        # Validate ownership/revision before spending the expensive-work quota.
        if _saved_for_write(actor, params.experiment_id).revision != params.revision:
            raise MCPValidationError("Experiment changed. Reload it before continuing.",
                                     code="progression_experiment_conflict")
        _comparison_quota(actor)

    def prepare(actor):
        # Simulations run without household locks; saving rechecks the revision.
        return _native(experiments.prepare_comparison, actor, params.experiment_id, params.revision)

    def persist(actor, evidence):
        experiment, comparison = _native(experiments.record_comparison, actor, params.experiment_id,
                                         params.revision, evidence)
        return experiment, "comparison", comparison.pk

    return _evidence(params, "compare_progression_experiment", precheck=precheck, prepare=prepare, persist=persist)


@tool()
@safe_tool
def get_progression_comparison(params: ProgressionComparisonIn) -> ProgressionComparisonOut:
    """Read one saved paired report and its current freshness without simulating."""
    actor = _actor()
    with authorized_household(actor, actor) as (fresh_actor, _):
        pass
    # Reports are multi-MB and freshness rebuilds the catalog, so the read runs
    # without household locks; authority and the saved report are rechecked
    # under them before the private report is returned.
    result = _call(experiments.get_comparison, fresh_actor, params.experiment_id, params.comparison_id)
    with authorized_household(actor, actor) as (fresh_actor, _):
        if not ProgressionComparison.objects.filter(
            pk=params.comparison_id, experiment_id=params.experiment_id,
            experiment__actor=fresh_actor, experiment__family_id=fresh_actor.family_id,
        ).exists():
            raise MCPNotFoundError("Comparison not found.")
        return result


@tool()
@safe_tool
def record_progression_decision(params: RecordProgressionDecisionIn) -> ProgressionExperimentOut:
    """Append a rationale, next action and review date against current saved evidence.

    Fresh revision/rules/catalog/evaluator evidence is required. Ready for design
    additionally requires passing configured targets; it grants no publication
    or live-change approval. Reuse request_id to avoid duplicate decisions.
    """
    def create(actor):
        experiment = _saved_for_write(actor, params.experiment_id)
        previous = set(experiment.decisions.values_list("pk", flat=True))
        _call(experiments.record_decision, actor, experiment.pk, params.model_dump(
            mode="json", exclude={"request_id", "experiment_id"},
        ), include_observations=False)
        decision = experiment.decisions.exclude(pk__in=previous).get()
        return experiment, "decision", decision.pk

    return _mutate(params, "record_progression_decision", create)


def _saved_for_write(actor, experiment_id):
    experiment = ProgressionExperiment.objects.filter(
        pk=experiment_id, actor=actor, family_id=actor.family_id,
    ).first()
    if experiment is None:
        raise MCPNotFoundError("Experiment not found.")
    if experiment.is_archived:
        raise MCPValidationError("This experiment is archived; restore it before making changes.",
                                 code="progression_experiment_conflict")
    return experiment


@tool()
@safe_tool
def capture_progression_observation(params: ProgressionExperimentMutationIn) -> ProgressionExperimentOut:
    """Save an immutable own-family accounting checkpoint, with author and read grants.

    The server captures the bounded installed-economy aggregate. Supply a stable
    request_id and the saved revision. An identical retry returns the current
    notebook without capturing again. No client-provided evidence is accepted.
    """
    require_scope("mcp:read")

    def prepare(actor):
        # The household aggregate runs without household locks; saving rechecks it.
        return _native(experiments.prepare_observation, actor, params.experiment_id, params.revision)

    def persist(actor, checkpoint):
        experiment, observation = _native(experiments.record_observation, actor, params.experiment_id,
                                          params.revision, checkpoint)
        return experiment, "observation", observation.pk

    return _evidence(params, "capture_progression_observation",
                     precheck=lambda actor: None, prepare=prepare, persist=persist)


@tool()
@safe_tool
def get_progression_observations(params: ProgressionObservationsIn) -> ProgressionObservationsOut:
    """Read bounded accounting and saved-work aggregates for all active family children.

    Requires mcp:read, accepts no account or family selector, and reads no journal
    or transaction prose. These are observations of installed rules, distinct
    from anonymous forecasts and saved candidate policies; no state is written.
    """
    require_scope("mcp:read")
    actor = _actor()
    with authorized_household(actor, actor) as (fresh_actor, _):
        pass
    # The bounded aggregate scans household ledgers for seconds, so it runs
    # without household locks; it is already not a repeatable-read snapshot.
    # Current authority is rechecked before the private aggregate is returned.
    result = _call(economy_observations, fresh_actor)
    with authorized_household(actor, actor):
        return result
