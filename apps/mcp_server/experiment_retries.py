"""Atomic UUID-result receipts for the native private progression notebook."""
from contextlib import contextmanager
import hashlib
import json
from types import SimpleNamespace

from django.db import DatabaseError, connection

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
        # Lock and prove the exact row without loading multi-MB report JSON.
        found = model is not None and model.objects.select_for_update(no_key=True).filter(
            pk=result_id, experiment=experiment,
        ).values_list("pk", flat=True).first() is not None
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
    return _commit_once(actor, operation, request_id, _digest(payload), create, serialize)


def experiment_evidence_once(*, actor, operation, request_id, payload, precheck, prepare, persist, serialize):
    """Like ``experiment_mutation_once``, with expensive evidence outside household locks.

    Comparisons and checkpoints take seconds to compute and their reports are
    large, and holding Family/member locks through that work stalled unrelated
    same-family activity. A request-scoped lock serializes only identical UUIDs:
    a duplicate waits for the first attempt and replays its receipt without
    recomputing, spending quota or saving again. Household locks cover the
    receipt check with the cheap ``precheck``, then the revalidated ``persist``
    write with its receipt; ``prepare`` runs between them without locks or a
    transaction. The response is read afterwards, and current authority and the
    saved result are rechecked under the locks before it is returned.
    """
    digest = _digest(payload)
    with _identical_request_lock(actor, operation, request_id):
        with authorized_household(actor, actor) as (fresh_actor, _):
            _require_staff_parent(fresh_actor)
            identity = _receipt_identity(fresh_actor, operation, request_id, digest)
            if identity is None:
                precheck(fresh_actor)
        if identity is None:
            prepared = prepare(fresh_actor)
            with authorized_household(actor, actor) as (fresh_actor, _):
                _require_staff_parent(fresh_actor)
                # Another worker may have committed this UUID if the request
                # lock was unavailable; never save the same request twice.
                identity = _receipt_identity(fresh_actor, operation, request_id, digest)
                if identity is None:
                    experiment, result_kind, result_id = persist(fresh_actor, prepared)
                    _record_receipt(fresh_actor, experiment, operation, request_id, digest, result_kind, result_id)
                    identity = (experiment.pk, result_kind, result_id)
        experiment_id, result_kind, result_id = identity
        response = serialize(fresh_actor, SimpleNamespace(pk=experiment_id), result_kind, result_id)
        with authorized_household(actor, actor) as (fresh_actor, _):
            _require_staff_parent(fresh_actor)
            _saved_result(fresh_actor, experiment_id, result_kind, result_id)
        return response


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=_request_value)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _require_staff_parent(actor):
    if actor.role != "parent" or not actor.is_staff:
        raise MCPPermissionDenied("Progression experiments require an active staff parent.")


def _receipt(actor, operation, request_id, digest):
    receipt = MCPExperimentMutationReceipt.objects.filter(
        actor=actor, operation=operation, request_id=request_id,
    ).first()
    if receipt is not None and (receipt.family_id != actor.family_id or receipt.request_digest != digest):
        raise MCPValidationError(
            "This request UUID was already used with different details or family.",
            code="idempotency_conflict",
        )
    return receipt


def _replay(actor, receipt, serialize):
    experiment = _saved_result(actor, receipt.experiment_id, receipt.result_kind, receipt.result_id)
    return serialize(actor, experiment, receipt.result_kind, receipt.result_id)


def _receipt_identity(actor, operation, request_id, digest):
    """Return a verified (experiment, kind, result) identity for a committed UUID."""
    receipt = _receipt(actor, operation, request_id, digest)
    if receipt is None:
        return None
    _saved_result(actor, receipt.experiment_id, receipt.result_kind, receipt.result_id)
    return receipt.experiment_id, receipt.result_kind, receipt.result_id


def _record_receipt(actor, experiment, operation, request_id, digest, result_kind, result_id):
    experiment = _saved_result(actor, experiment.pk, result_kind, result_id)
    MCPExperimentMutationReceipt.objects.create(
        family_id=actor.family_id, actor=actor, experiment=experiment,
        operation=operation, request_id=request_id, request_digest=digest,
        result_kind=result_kind, result_id=result_id,
    )
    return experiment


def _commit_once(actor, operation, request_id, digest, create, serialize):
    with authorized_household(actor, actor) as (fresh_actor, _):
        _require_staff_parent(fresh_actor)
        receipt = _receipt(fresh_actor, operation, request_id, digest)
        if receipt is not None:
            return _replay(fresh_actor, receipt, serialize)

        experiment, result_kind, result_id = create(fresh_actor)
        experiment = _record_receipt(fresh_actor, experiment, operation, request_id, digest, result_kind, result_id)
        return serialize(fresh_actor, experiment, result_kind, result_id)


@contextmanager
def _identical_request_lock(actor, operation, request_id):
    """Serialize one actor's identical request UUID across workers without row locks.

    A PostgreSQL session advisory lock is held across the unlocked computation
    and released explicitly, because pooled connections outlive the request.
    Other databases rely on the receipt recheck before saving.
    """
    if connection.vendor != "postgresql":
        yield
        return
    name = f"abby-mcp-experiment-request:{actor.pk}:{operation}:{request_id}"
    key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [key])
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
        except DatabaseError:
            # Ending the session releases its advisory locks.
            connection.close()
