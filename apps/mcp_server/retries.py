"""Atomic MCP write receipts with current authorization and deletion tombstones."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.families.models import Family

from .errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from .models import MCPMutationReceipt


MAX_RESPONSE_BYTES = 256 * 1024


def _request_value(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported request value: {type(value).__name__}")


def mutation_once(*, actor, target, operation, request_id, payload, result_model,
                  target_field="user_id", shared_target_request=False, create, serialize):
    """Commit the domain operation and immutable response in one transaction.

    Family -> sorted member locks match account-lifecycle ordering. Replays
    revalidate current membership/roles and source ownership, including calls
    authenticated before a concurrent departure or reassignment. Most UUIDs
    belong to an actor/operation; movement shares the native target/UUID
    identity across authorized callers. Neither may cross a family boundary.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_request_value)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    User = get_user_model()
    with transaction.atomic():
        family = Family.objects.select_for_update(no_key=True).filter(pk=actor.family_id).first()
        if family is None:
            raise MCPPermissionDenied("Your family is no longer available.")
        members = {
            member.pk: member for member in User.objects.select_for_update(no_key=True).filter(
                pk__in={actor.pk, target.pk}, family=family,
            ).order_by("pk")
        }
        fresh_actor, fresh_target = members.get(actor.pk), members.get(target.pk)
        if (fresh_actor is None or not fresh_actor.is_active
                or (fresh_actor.role, fresh_actor.is_staff) != (actor.role, actor.is_staff)):
            raise MCPPermissionDenied("Your account permissions have changed. Reconnect before retrying.")
        if fresh_target is None or fresh_target.role != target.role:
            raise MCPNotFoundError("The target account is no longer available in your family.")
        if fresh_actor.role != "parent" and fresh_target.pk != fresh_actor.pk:
            raise MCPPermissionDenied("Children can only change their own records.")

        identity = {"target": fresh_target} if shared_target_request else {"actor": fresh_actor}
        receipt = MCPMutationReceipt.objects.filter(
            **identity, operation=operation, request_id=request_id,
        ).first()
        if receipt is not None:
            if receipt.family_id != family.pk or receipt.target_id != fresh_target.pk or receipt.request_digest != digest:
                raise MCPValidationError(
                    "This request UUID was already used with different details or family.",
                    code="idempotency_conflict",
                )
            if receipt.response is None or receipt.result_model != result_model._meta.label_lower:
                raise MCPNotFoundError("The original result was deleted; this request UUID cannot be reused.")
            original = result_model.objects.select_for_update().filter(
                pk=receipt.result_id, **{target_field: fresh_target.pk},
            ).first()
            if original is None:
                # Preserve deduplication even when a source was removed by a
                # non-ORM operation, or its owner subsequently changed.
                raise MCPNotFoundError("The original result is no longer available to this request.")
            return copy.deepcopy(receipt.response)

        result = create(fresh_actor, fresh_target)
        response = serialize(result)
        if len(json.dumps(response, ensure_ascii=False).encode()) > MAX_RESPONSE_BYTES:
            raise MCPValidationError("The result exceeds the retry receipt size limit; submit a smaller operation.")
        MCPMutationReceipt.objects.create(
            family=family, actor=fresh_actor, target=fresh_target, operation=operation,
            request_id=request_id, request_digest=digest,
            result_model=result._meta.label_lower, result_id=result.pk, response=response,
        )
        return response


def clear_deleted_mutation_response(sender, instance, using, **kwargs):
    """A deleted source must not leave a private snapshot or allow replay."""
    MCPMutationReceipt.objects.using(using).filter(
        result_model=sender._meta.label_lower, result_id=instance.pk,
    ).update(response=None)


def clear_deleted_member_responses(sender, instance, using, **kwargs):
    """Shared project snapshots may contain other household members' names.

    Clear all family snapshots on a member deletion, including responses for
    surviving actors/targets. Tombstones continue to prevent duplicate writes.
    """
    receipts = MCPMutationReceipt.objects.using(using)
    receipts.filter(actor_id=instance.pk).exclude(operation="log_movement_session").delete()
    receipts.filter(family_id=instance.family_id).update(response=None)
