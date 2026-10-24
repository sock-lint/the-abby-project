"""Review and publish one explicit canonical challenge identity mapping."""
from pydantic import ValidationError

from apps.quests import reconciliation
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPackError

from ..context import require_staff_parent
from ..errors import MCPError, MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..reconciliation_schemas import (
    ChallengeReconciliationOut, GetChallengeReconciliationIn,
    PreviewChallengeReconciliationIn, PublishChallengeReconciliationIn,
)
from ..server import tool
from ..shapes import to_plain


def _call(function, *args, **kwargs):
    # The native service owns its mutex-first lock order and fresh authority.
    # Taking household/member locks in this adapter would invert that order.
    try:
        result = to_plain(function(*args, **kwargs))
    except ContentAuthorPermissionDenied as exc:
        raise MCPPermissionDenied(str(exc)) from None
    except ContentObjectNotFound as exc:
        raise MCPNotFoundError(str(exc)) from None
    except reconciliation.ReconciliationConflict as exc:
        raise MCPValidationError(str(exc), code="challenge_reconciliation_conflict") from None
    except ContentPackError as exc:
        raise MCPValidationError(str(exc)) from None
    try:
        return ChallengeReconciliationOut.model_validate(result).model_dump(mode="json", exclude_unset=True)
    except ValidationError:
        # Producer/schema mismatches must never echo unexpected private fields.
        raise MCPError("The reconciliation result could not be returned safely.", code="internal_error") from None


@tool()
@safe_tool
def preview_challenge_reconciliation(params: PreviewChallengeReconciliationIn) -> ChallengeReconciliationOut:
    """Preview one explicit global source-to-canonical challenge pair without changing it.

    Reuse client_request_id after an uncertain response. The private receipt
    contains global definitions and preserves accepted history and creator
    provenance. Cooperation differences are displayed for acknowledgement at
    publication; no household usage records or counts are returned.
    """
    return _call(
        reconciliation.preview_reconciliation, require_staff_parent(),
        params.source_definition_id, params.canonical_definition_id, params.client_request_id,
    )


@tool()
@safe_tool
def get_challenge_reconciliation(params: GetChallengeReconciliationIn) -> ChallengeReconciliationOut:
    """Read this author's same-family reconciliation receipt after fresh authorization.

    Use its preview_id to recover an uncertain preview or publication response.
    This does not publish, refresh an expired preview or reveal household usage.
    """
    return _call(reconciliation.get_reconciliation, require_staff_parent(), params.preview_id)


@tool()
@safe_tool
def publish_challenge_reconciliation(params: PublishChallengeReconciliationIn) -> ChallengeReconciliationOut:
    """Publish the exact reviewed identity mapping with explicit transport confirmation.

    If the preview requires cooperation acknowledgement, also set
    acknowledge_cooperative_transition=true. Saved windows, rewards and creator
    provenance remain intact. Reuse the same receipt, digest and acknowledgement
    after an uncertain response; exact completed retries do not apply again.
    """
    return _call(
        reconciliation.publish_reconciliation, require_staff_parent(),
        params.preview_id, params.content_digest,
        acknowledge_cooperative_transition=params.acknowledge_cooperative_transition,
    )
