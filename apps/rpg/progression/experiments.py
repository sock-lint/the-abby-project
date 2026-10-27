"""A bounded private notebook of anonymous forecasts and decisions.

Only this module writes notebook rows. Domain award writers are never called.
The paired reports share one detached catalog; client reports are not evidence.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date
import hashlib
import json
import uuid

from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.quests.activity import household_timezone
from apps.rpg.authoring_archive import MAX_ARCHIVED, ensure_active_capacity, list_authoring, locked_author
from apps.rpg.models import ProgressionComparison, ProgressionDecision, ProgressionExperiment, ProgressionObservation
from .catalog import load_catalog
from .engine import ENGINE_VERSION, MAX_WORK_UNITS, estimate_work, normalize_config, pet_incubation_policy, rules_fingerprint, simulate_progression
from .feedback import evaluate_comparison, feedback_fingerprint, feedback_metadata, normalize_targets

MAX_EXPERIMENTS = 20
MAX_COMPARISONS = 20
MAX_DECISIONS = 100
MAX_OBSERVATIONS = 20
MAX_COMPARISON_WORK_UNITS = MAX_WORK_UNITS * 2
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
GATE_POLICIES = {"milestone_gates": "milestones", "tenure_gates": "milestone_tenure"}


class ExperimentConflict(Exception):
    pass


class ExperimentNotFound(Exception):
    pass


class ExperimentUnavailable(Exception):
    pass


def _actor(actor, *, lock=False):
    if lock:
        return locked_author(actor)
    queryset = User.objects
    current = queryset.filter(pk=actor.pk, family_id=actor.family_id, is_active=True, is_staff=True, role="parent").first()
    if current is None:
        raise PermissionDenied("Progression experiments are available to active staff parents.")
    return current


def _experiment(actor, experiment_id, *, lock=False):
    queryset = ProgressionExperiment.objects.filter(actor=actor, family_id=actor.family_id)
    if lock:
        queryset = queryset.select_for_update()
    experiment = queryset.filter(pk=experiment_id).first()
    if experiment is None:
        raise ExperimentNotFound("Experiment not found.")
    return experiment


def _revision(experiment, revision):
    if experiment.is_archived:
        raise ExperimentConflict("This experiment is archived and read-only. Restore it before making changes.")
    if type(revision) is not int or experiment.revision != revision:
        raise ExperimentConflict("Experiment changed. Reload it before continuing.")


def _text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must contain 1–{limit} characters.")
    return value.strip()


def _candidate_config(config, policy, daily, expedition_budget):
    if policy in GATE_POLICIES:
        return {**config, "challenge_gates": {**deepcopy(config["challenge_gates"]), "mode": GATE_POLICIES[policy]}}
    if policy == "expedition_limits":
        return {**config, "expedition_budget": deepcopy(expedition_budget)}
    return {**config, "reward_budget": {"daily_coins": None if policy == "commitment100" else daily},
            "reward_commitment": {"enabled": policy == "commitment100"}}


def _inputs(data, *, default_policy="envelope", default_expedition_budget=None):
    from .expedition_budget import normalize_expedition_budget

    config = normalize_config(data["config"])
    # Persist the installed control independently from any imported scenario.
    # The selected candidate policy establishes the one hypothetical change.
    policy = data.get("candidate_policy", default_policy)
    if not isinstance(policy, str) or policy not in {"envelope", "commitment100", "expedition_limits", *GATE_POLICIES}:
        raise ValueError("Choose a supported Coin, expedition or challenge-gate candidate policy.")
    supplied_budget = (data["candidate_expedition_budget"] if "candidate_expedition_budget" in data
                       else default_expedition_budget if default_expedition_budget is not None else {})
    if not isinstance(supplied_budget, dict):
        raise ValueError("Candidate expedition budget must be an object.")
    expedition_budget = normalize_expedition_budget(supplied_budget)
    unlimited = normalize_expedition_budget({})
    daily = data["candidate_daily_coins"]
    if policy in GATE_POLICIES:
        if daily is not None or expedition_budget != unlimited:
            raise ValueError("Challenge-gate comparisons require null candidate daily Coins and no separate candidate expedition quota.")
        if not config["challenge_gates"]["rules"]:
            raise ValueError("Add at least one challenge-gate rule before saving this comparison.")
        # Keep the entire recipe in both arms. Only the mode differs, so the
        # same seed, catalog, Coin policy and expedition caps remain comparable.
        config["challenge_gates"]["mode"] = "current"
    elif policy == "expedition_limits":
        if daily is not None or expedition_budget == unlimited:
            raise ValueError("Expedition-limit comparisons require null candidate daily Coins and at least one quota.")
    else:
        if expedition_budget != unlimited or config["expedition_budget"] != unlimited:
            raise ValueError("Choose expedition_limits to compare quotas separately from Coin rules.")
        if type(daily) is not int or not 0 <= daily <= 100000:
            raise ValueError("Candidate daily Coins must be a whole number from 0 to 100000.")
        config["reward_budget"] = {"daily_coins": None}
        config["reward_commitment"] = {"enabled": False}
    # A quota comparison retains the routine's Coin rules in both arms.
    if policy not in GATE_POLICIES:
        config["expedition_budget"] = unlimited
    if policy == "commitment100" and daily != 100:
        raise ValueError("The commitment prototype requires exactly 100 candidate daily Coins.")
    candidate = _candidate_config(config, policy, daily, expedition_budget)
    normalize_config(candidate)
    if estimate_work(config) + estimate_work(candidate) > MAX_COMPARISON_WORK_UNITS:
        raise ValueError("Paired comparison exceeds its work limit. Reduce trials or activity counts.")
    return {
        "name": _text(data["name"], "Name", 100),
        "hypothesis": _text(data["hypothesis"], "Hypothesis", 2000),
        "config": config,
        "candidate_daily_coins": daily,
        "candidate_policy": policy,
        "candidate_expedition_budget": expedition_budget,
        "targets": normalize_targets(data["targets"]),
    }


def _snapshot(experiment):
    return {key: deepcopy(getattr(experiment, key)) for key in (
        "name", "hypothesis", "config", "candidate_daily_coins", "candidate_policy", "candidate_expedition_budget", "targets",
    )}


def _binding(catalog, *, incubation_policy=None):
    return {"engine_version": ENGINE_VERSION, "rules_fingerprint": rules_fingerprint(incubation_policy=incubation_policy),
            "feedback_fingerprint": feedback_fingerprint(),
            "catalog_fingerprint": catalog.fingerprint,
            "source_commit": getattr(settings, "SOURCE_COMMIT", "") or "unavailable"}


_REQUEST_BINDING = ContextVar("progression_request_binding", default=None)


def _read_binding():
    try:
        return _binding(load_catalog())
    except ValueError:
        # Historical evidence remains readable if today's catalog is invalid.
        # Unknown freshness can never authorize a new decision.
        return None


def _current_binding():
    preset = _REQUEST_BINDING.get()
    return preset[0] if preset is not None else _read_binding()


# Source rows, rather than accepted catalog rows, also cover eligibility changes
# and previously excluded definitions becoming available. No household records or
# private authoring/pack metadata enter this short-lived optimistic token.
_CATALOG_SOURCE_LIMITS = {
    "achievements.SkillCategory": 2048, "achievements.Subject": 8192,
    "achievements.Skill": 2048, "achievements.SkillPrerequisite": 32768,
    "achievements.Badge": 512, "pets.PetSpecies": 256,
    "pets.PotionType": 256, "rpg.ItemDefinition": 4096,
    "rpg.DropTable": 16384, "quests.QuestDefinition": 4096,
    "quests.QuestSkillTag": 32768, "quests.QuestRewardItem": 32768,
}


def _catalog_sources():
    sources = [(apps.get_model(label), limit) for label, limit in _CATALOG_SOURCE_LIMITS.items()]
    species = apps.get_model("pets.PetSpecies")
    sources.append((species.available_potions.through, 65536))
    return sorted(sources, key=lambda source: source[0]._meta.db_table)


def _catalog_source_token():
    """Bounded source versions, used only within one decision request.

    PostgreSQL's row versions detect updates even when a writer restores the
    original values. They avoid copying catalog descriptions/report-sized JSON
    under household locks. Portable tests use exact concrete values instead.
    """
    rows = []
    for model, limit in _catalog_sources():
        queryset = model.objects.order_by("pk")
        label = model._meta.label_lower
        if label == "quests.questdefinition":
            queryset = queryset.filter(is_system=True)
        elif label in {"quests.questskilltag", "quests.questrewarditem"}:
            queryset = queryset.filter(quest_definition__is_system=True)
        if connection.vendor == "postgresql":
            table = connection.ops.quote_name(model._meta.db_table)
            queryset = queryset.annotate(_source_version=RawSQL(
                f"{table}.xmin::text || '/' || {table}.ctid::text", [],
            ))
            values = list(queryset.values_list("pk", "_source_version")[:limit + 1])
        else:
            values = list(queryset.values_list(*[field.attname for field in model._meta.concrete_fields])[:limit + 1])
        if len(values) > limit:
            raise ValueError("Global catalog source exceeds the decision freshness limit.")
        rows.append((label, values))
    policy = {"incubation": dict(pet_incubation_policy()),
              "asset_support": getattr(settings, "RPG_ASSET_SUPPORT_POLICY", None),
              "coins_per_hour": settings.COINS_PER_HOUR, "coins_per_dollar": settings.COINS_PER_DOLLAR,
              "badge_coins": settings.COINS_PER_BADGE_RARITY}
    return hashlib.sha256(json.dumps([rows, policy], sort_keys=True, default=str).encode()).hexdigest()


@contextmanager
def request_catalog_binding(*, for_decision=False):
    """Snapshot today's global catalog binding once, before callers take household locks.

    The snapshot takes a substantial fraction of a second and holds no
    household data. Within the block every freshness check and report reuses
    it, so lock holders never rebuild the catalog. Callers without the block,
    including native reads, keep computing it on demand. A decision additionally
    binds the source versions around that computation; its final short catalog
    fence validates those versions before any decision is appended.
    """
    source_token = None
    if for_decision:
        try:
            # A shared read fence prevents transient insert/delete generations
            # from appearing in the detached projection and disappearing before
            # its source stamp. This transaction ends BEFORE any caller takes
            # household locks; simulations are never performed here.
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    tables = ", ".join(connection.ops.quote_name(model._meta.db_table)
                                       for model, _ in _catalog_sources())
                    with connection.cursor() as cursor:
                        cursor.execute("LOCK TABLE " + tables + " IN SHARE MODE")
                binding = _read_binding()
                source_token = _catalog_source_token()
        except ValueError:
            binding = None
    else:
        binding = _current_binding()
    token = _REQUEST_BINDING.set((binding, source_token) if for_decision else (binding,))
    try:
        yield
    finally:
        _REQUEST_BINDING.reset(token)


def _stale(experiment, comparison, binding=None):
    return experiment.revision != comparison.experiment_revision or (
        binding is not None and any(comparison.binding.get(key) != binding.get(key)
                                   for key in ("engine_version", "rules_fingerprint", "catalog_fingerprint", "feedback_fingerprint"))
    )


def _decision_json(decision):
    return {"id": str(decision.pk), "comparison_id": str(decision.comparison_id), "outcome": decision.outcome,
            "rationale": decision.rationale, "next_action": decision.next_action,
            "review_on": decision.review_on.isoformat(), "created_at": decision.created_at.isoformat()}


def _summary(experiment):
    decision = experiment.decisions.order_by("-created_at", "-id").first()
    return {"id": str(experiment.pk), "name": experiment.name, "hypothesis": experiment.hypothesis,
            "revision": experiment.revision, "is_archived": experiment.is_archived, "updated_at": experiment.updated_at.isoformat(),
            "latest_decision": _decision_json(decision) if decision else None}


def _compact_report(report):
    """Store repeated trace column names once, retaining every daily value.

    Only oversized comparisons use this private storage representation. Native
    reports, evaluators and API consumers continue to receive ordinary rows.
    Unknown/nonrectangular traces keep their original form and storage guard.
    """
    trace = report.get("trace") if isinstance(report, dict) else None
    if not isinstance(trace, list) or not trace or not isinstance(trace[0], dict):
        return report
    columns = list(trace[0])
    if (not all(isinstance(key, str) for key in columns)
            or any(not isinstance(row, dict) or list(row) != columns for row in trace)):
        return report
    return {**report, "trace": {"storage_format": "trace_columns_v1", "columns": columns,
                                "rows": [[row[column] for column in columns] for row in trace]}}


def _restore_report(report):
    """Expand new evidence without rewriting legacy, already stored reports."""
    trace = report.get("trace") if isinstance(report, dict) else None
    if not isinstance(trace, dict) or trace.get("storage_format") != "trace_columns_v1":
        return report
    columns, rows = trace.get("columns"), trace.get("rows")
    if (set(trace) != {"storage_format", "columns", "rows"}
            or not isinstance(columns, list) or not all(isinstance(key, str) for key in columns)
            or len(set(columns)) != len(columns) or not isinstance(rows, list)
            or any(not isinstance(row, list) or len(row) != len(columns) for row in rows)):
        raise ExperimentUnavailable("Saved comparison trace is invalid. Its evidence has not been changed.")
    return {**report, "trace": [dict(zip(columns, row, strict=True)) for row in rows]}


def _comparison_json(experiment, comparison, *, full=False, binding=None):
    result = {"id": str(comparison.pk), "experiment_revision": comparison.experiment_revision,
              "created_at": comparison.created_at.isoformat(), "evaluation": comparison.evaluation,
              "stale": binding is None or _stale(experiment, comparison, binding),
              "freshness": "unavailable" if binding is None else "stale" if _stale(experiment, comparison, binding) else "current",
              "binding": comparison.binding}
    if full:
        result.update(inputs=comparison.inputs, control=_restore_report(comparison.control),
                      candidate=_restore_report(comparison.candidate))
    return result


def _detail(experiment, *, include_observations=True):
    comparisons = list(experiment.comparisons.defer("control", "candidate", "inputs").order_by("-created_at", "-id"))
    binding = _current_binding() if comparisons else None
    return {**_summary(experiment), **_snapshot(experiment),
            "comparisons": [_comparison_json(experiment, row, binding=binding) for row in comparisons],
            "decisions": [_decision_json(row) for row in experiment.decisions.order_by("-created_at", "-id")],
            "observations": [{"id": str(row.pk), "created_at": row.created_at.isoformat(),
                              "experiment_revision": row.experiment_revision, "status": row.payload["status"],
                              "payload": row.payload, "binding": row.binding}
                             for row in experiment.observations.order_by("-created_at", "-id")] if include_observations else []}


@transaction.atomic
def list_experiments(actor, *, include_archived=False, after=None, limit=20):
    page = list_authoring(actor, "experiment", include_archived=include_archived, after=after, limit=limit)
    rows = ProgressionExperiment.objects.filter(pk__in=[row["id"] for row in page["rows"]]).order_by("pk")
    return {"schema_version": 1, "limits": {"max_experiments": MAX_EXPERIMENTS, "max_archived_experiments": MAX_ARCHIVED, "max_comparisons": MAX_COMPARISONS,
            "max_observations": MAX_OBSERVATIONS,
            "max_comparison_work_units": MAX_COMPARISON_WORK_UNITS, "max_evidence_bytes": MAX_EVIDENCE_BYTES}, "feedback": feedback_metadata(),
            "experiments": [_summary(row) for row in rows],
            "total": page["total"], "has_more": page["has_more"], "next_after": page["next_after"]}


@transaction.atomic
def create_experiment(actor, data, *, include_observations=True):
    values = _inputs(data)
    actor = _actor(actor, lock=True)
    ensure_active_capacity("experiment", actor, limit=MAX_EXPERIMENTS)
    return _detail(ProgressionExperiment.objects.create(actor=actor, family_id=actor.family_id, **values),
                   include_observations=include_observations)


def get_experiment(actor, experiment_id, *, include_observations=True):
    return _detail(_experiment(_actor(actor), experiment_id), include_observations=include_observations)


@transaction.atomic
def save_experiment(actor, experiment_id, revision, data, *, include_observations=True):
    actor = _actor(actor, lock=True)
    experiment = _experiment(actor, experiment_id, lock=True)
    _revision(experiment, revision)
    # Older clients omit this new choice. Preserve the stored policy under
    # the experiment lock rather than silently reverting their selection.
    values = _inputs(data, default_policy=experiment.candidate_policy,
                     default_expedition_budget=experiment.candidate_expedition_budget)
    for key, value in values.items():
        setattr(experiment, key, value)
    experiment.revision += 1
    experiment.save(update_fields=[*values, "revision", "updated_at"])
    return _detail(experiment, include_observations=include_observations)


def compare_experiment(actor, experiment_id, revision):
    evidence = prepare_comparison(actor, experiment_id, revision)
    experiment, comparison = record_comparison(actor, experiment_id, revision, evidence)
    return _comparison_json(experiment, comparison, full=True, binding=evidence["binding"])


def prepare_comparison(actor, experiment_id, revision):
    """Simulate paired evidence without taking locks; ``record_comparison`` commits it."""
    actor = _actor(actor)
    experiment = _experiment(actor, experiment_id)
    _revision(experiment, revision)
    if experiment.comparisons.count() >= MAX_COMPARISONS:
        raise ValueError("This experiment has reached its 20-comparison limit.")
    inputs = _inputs(_snapshot(experiment))
    control_config = inputs["config"]
    candidate_config = _candidate_config(control_config, inputs["candidate_policy"], inputs["candidate_daily_coins"],
                                         inputs["candidate_expedition_budget"])
    try:
        catalog = load_catalog()
    except ValueError as exc:
        raise ExperimentUnavailable(str(exc)) from exc
    incubation_policy = pet_incubation_policy()
    binding = _binding(catalog, incubation_policy=incubation_policy)
    control = simulate_progression(control_config, catalog=catalog, incubation_policy=incubation_policy)
    candidate = simulate_progression(candidate_config, catalog=catalog, incubation_policy=incubation_policy)
    evaluation = evaluate_comparison(control, candidate, inputs["targets"])
    evidence = {"inputs": inputs, "control": control, "candidate": candidate,
                "evaluation": evaluation, "binding": binding}
    if len(json.dumps(evidence).encode()) > MAX_EVIDENCE_BYTES:
        control, candidate = _compact_report(control), _compact_report(candidate)
        evidence.update(control=control, candidate=candidate)
    if len(json.dumps(evidence).encode()) > MAX_EVIDENCE_BYTES:
        raise ValueError("Comparison evidence exceeds the 4 MiB storage limit. Simplify the routine or reduce the horizon.")
    return evidence


def record_comparison(actor, experiment_id, revision, evidence):
    """Recheck current authority, revision and limits under locks, then save prepared evidence."""
    with transaction.atomic():
        actor = _actor(actor, lock=True)
        experiment = _experiment(actor, experiment_id, lock=True)
        _revision(experiment, revision)
        if experiment.comparisons.count() >= MAX_COMPARISONS:
            raise ValueError("This experiment has reached its 20-comparison limit.")
        comparison = ProgressionComparison.objects.create(
            experiment=experiment, experiment_revision=revision, inputs=evidence["inputs"],
            control=evidence["control"], candidate=evidence["candidate"],
            evaluation=evidence["evaluation"], binding=evidence["binding"],
        )
    return experiment, comparison


def get_comparison(actor, experiment_id, comparison_id):
    experiment = _experiment(_actor(actor), experiment_id)
    comparison = experiment.comparisons.filter(pk=comparison_id).first()
    if comparison is None:
        raise ExperimentNotFound("Comparison not found.")
    return _comparison_json(experiment, comparison, full=True, binding=_current_binding())


def record_decision(actor, experiment_id, data, *, include_observations=True):
    # REST callers need the same detached preparation as MCP. An ordinary read
    # binding is insufficient; never upgrade a cached read into commit proof.
    preset = _REQUEST_BINDING.get()
    if preset is None or len(preset) < 2:
        with request_catalog_binding(for_decision=True):
            return _record_decision(actor, experiment_id, data, include_observations=include_observations)
    return _record_decision(actor, experiment_id, data, include_observations=include_observations)


@transaction.atomic
def _record_decision(actor, experiment_id, data, *, include_observations=True):
    actor = _actor(actor, lock=True)
    # Match authoring's Family -> author -> catalog order. The existing fence
    # blocks supported and raw catalog writers through this transaction's save;
    # no simulation, catalog projection or source inspection runs under it.
    from apps.rpg.content.publication import _catalog_lock
    _catalog_lock()
    binding, source_token = _REQUEST_BINDING.get()
    if binding is None or source_token is None:
        raise ExperimentUnavailable("Current catalog is unavailable. Saved evidence remains readable; retry the decision after the catalog recovers.")
    try:
        current_token = _catalog_source_token()
    except ValueError as error:
        raise ExperimentUnavailable("Current catalog is unavailable. Retry the decision after the catalog recovers.") from error
    if current_token != source_token:
        raise ExperimentConflict("Catalog changed after checking evidence. Run a new comparison before recording a decision.")
    experiment = _experiment(actor, experiment_id, lock=True)
    _revision(experiment, data["revision"])
    try:
        comparison_id = uuid.UUID(str(data["comparison_id"]))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Choose a saved comparison.") from exc
    # The decision needs only the revision, binding and evaluation, not the report.
    comparison = experiment.comparisons.defer("control", "candidate", "inputs").filter(pk=comparison_id).first()
    if comparison is None:
        raise ExperimentNotFound("Comparison not found.")
    if _stale(experiment, comparison, binding):
        raise ExperimentConflict("Evidence is stale. Run a new comparison before recording a decision.")
    outcome = data["outcome"]
    if not isinstance(outcome, str) or outcome not in {"keep_testing", "revise", "ready_for_design"}:
        raise ValueError("Choose keep testing, revise, or ready for design.")
    if outcome == "ready_for_design" and comparison.evaluation["status"] != "pass":
        raise ValueError("Ready for design requires configured, passing simulation targets. It does not approve live changes.")
    rationale = _text(data["rationale"], "Rationale", 2000)
    next_action = _text(data["next_action"], "Next action", 2000)
    try:
        if not isinstance(data["review_on"], str):
            raise ValueError()
        review_on = date.fromisoformat(data["review_on"])
    except (ValueError, TypeError) as exc:
        raise ValueError("Choose a review date in YYYY-MM-DD format.") from exc
    today = timezone.localdate(timezone=household_timezone(actor))
    if review_on < today:
        raise ValueError("Review date cannot be in the past.")
    if experiment.decisions.count() >= MAX_DECISIONS:
        raise ValueError("This experiment has reached its 100-decision limit.")
    ProgressionDecision.objects.create(experiment=experiment, comparison=comparison, outcome=outcome,
                                     rationale=rationale, next_action=next_action, review_on=review_on)
    return _detail(experiment, include_observations=include_observations)


def capture_observation(actor, experiment_id, revision, *, include_observations=True):
    checkpoint = prepare_observation(actor, experiment_id, revision)
    # Keep the detail inside the save's actor/experiment locks, as before.
    with transaction.atomic():
        experiment, _ = record_observation(actor, experiment_id, revision, checkpoint)
        return _detail(experiment, include_observations=include_observations)


def prepare_observation(actor, experiment_id, revision):
    """Aggregate the household checkpoint without taking locks; ``record_observation`` commits it."""
    from .observations import economy_observations

    actor = _actor(actor)
    experiment = _experiment(actor, experiment_id)
    _revision(experiment, revision)
    if experiment.observations.count() >= MAX_OBSERVATIONS:
        raise ValueError("This experiment has reached its 20-observation checkpoint limit.")
    payload = economy_observations(actor)
    binding = {"source_commit": getattr(settings, "SOURCE_COMMIT", "") or "unavailable",
               "rules_fingerprint": rules_fingerprint(), "feedback_fingerprint": feedback_fingerprint(),
               "policy": "installed_uncapped", "scope": "own_family_active_children"}
    return {"payload": payload, "binding": binding}


def record_observation(actor, experiment_id, revision, checkpoint):
    """Recheck current authority, revision and limits under locks, then save a prepared checkpoint."""
    with transaction.atomic():
        actor = _actor(actor, lock=True)
        experiment = _experiment(actor, experiment_id, lock=True)
        _revision(experiment, revision)
        if experiment.observations.count() >= MAX_OBSERVATIONS:
            raise ValueError("This experiment has reached its 20-observation checkpoint limit.")
        observation = ProgressionObservation.objects.create(
            experiment=experiment, experiment_revision=revision,
            payload=checkpoint["payload"], binding=checkpoint["binding"],
        )
    return experiment, observation
