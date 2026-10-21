"""Atomic UUID-result receipts for the native private progression notebook."""
import hashlib
import json

from apps.rpg.models import (
    ProgressionComparison, ProgressionDecision, ProgressionExperiment, ProgressionObservation,
)

from .errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from .models import MCPExperimentMutationReceipt
from .retries import _request_value, authorized_household


_RESULT_MODELS = {
    "comparison": ProgressionComparison,
    "decision": ProgressionDecision,
    "observation": ProgressionObservation,
}


def _saved_result(actor, experiment_id, result_kind, result_id):
    experiment = ProgressionExperiment.objects.select_for_update(no_key=True).filter(
        pk=experiment_id, actor=actor, family_id=actor.family_id,
    ).first()
    if experiment is None:
        raise MCPNotFoundError("The original experiment is no longer available to this request.")
    if result_kind == "experiment":
        found = str(result_id) == str(experiment.pk)
    else:
        model = _RESULT_MODELS.get(result_kind)
        found = model is not None and model.objects.select_for_update(no_key=True).filter(
            pk=result_id, experiment=experiment,
        ).first() is not None
    if not found:
        raise MCPNotFoundError("The original saved result was deleted; this request UUID cannot be reused.")
    return experiment


def experiment_mutation_once(*, actor, operation, request_id, payload, create, serialize):
    """Commit native writes and compact identities, then reread authorized state.

    Family/member locks serialize identical requests and membership changes.
    Native services retain revisions, simulation bounds and ownership checks.
    Replays never rerun simulation, consume quota, append decisions/checkpoints,
    or cache household observation payloads under an author-only permission.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=_request_value)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    with authorized_household(actor, actor) as (fresh_actor, _):
        if fresh_actor.role != "parent" or not fresh_actor.is_staff:
            raise MCPPermissionDenied("Progression experiments require an active staff parent.")
        receipt = MCPExperimentMutationReceipt.objects.filter(
            actor=fresh_actor, operation=operation, request_id=request_id,
        ).first()
        if receipt is not None:
            if receipt.family_id != fresh_actor.family_id or receipt.request_digest != digest:
                raise MCPValidationError(
                    "This request UUID was already used with different details or family.",
                    code="idempotency_conflict",
                )
            experiment = _saved_result(fresh_actor, receipt.experiment_id,
                                       receipt.result_kind, receipt.result_id)
            return serialize(fresh_actor, experiment, receipt.result_kind, receipt.result_id)

        experiment, result_kind, result_id = create(fresh_actor)
        experiment = _saved_result(fresh_actor, experiment.pk, result_kind, result_id)
        MCPExperimentMutationReceipt.objects.create(
            family_id=fresh_actor.family_id, actor=fresh_actor, experiment=experiment,
            operation=operation, request_id=request_id, request_digest=digest,
            result_kind=result_kind, result_id=result_id,
        )
        return serialize(fresh_actor, experiment, result_kind, result_id)
