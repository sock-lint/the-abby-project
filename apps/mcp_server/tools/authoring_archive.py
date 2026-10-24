"""Archive private work without deleting evidence or changing published content."""
from apps.rpg.authoring_archive import (
    AuthoringArchiveConflict, AuthoringArchiveRequestConflict, set_archived,
)
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPackError

from ..archive_schemas import ArchiveDraftIn, ArchiveExperimentIn, AuthoringArchiveOut
from ..context import require_staff_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..server import tool


def _set(kind, params):
    try:
        return set_archived(require_staff_parent(), kind,
                            getattr(params, "draft_id", None) or params.experiment_id,
                            params.revision, params.is_archived, params.request_id, confirmation=True)
    except ContentAuthorPermissionDenied as error:
        raise MCPPermissionDenied(str(error)) from error
    except ContentObjectNotFound as error:
        raise MCPNotFoundError(str(error)) from error
    except AuthoringArchiveRequestConflict as error:
        raise MCPValidationError(str(error), code="idempotency_conflict") from error
    except AuthoringArchiveConflict as error:
        raise MCPValidationError(str(error), code="authoring_archive_conflict") from error
    except ContentPackError as error:
        raise MCPValidationError(str(error)) from error


@tool()
@safe_tool
def set_content_draft_archived(params: ArchiveDraftIn) -> AuthoringArchiveOut:
    """Archive or restore an owned content draft with confirmation and a stable UUID.

    Set is_archived=false to restore. Archives retain previews, simulations and
    publication receipts; published content remains live. The current revision
    changes on a state transition. Replay returns current state plus the original
    operation receipt, without reapplying it. Archived drafts are read-only.
    """
    return _set("content", params)


@tool()
@safe_tool
def set_editorial_draft_archived(params: ArchiveDraftIn) -> AuthoringArchiveOut:
    """Archive or restore an owned editorial draft with confirmation and a stable UUID.

    Published copy remains live; exact reads retain all review/publication history.
    Replay reports current state and the original operation without reapplying it.
    Restore requires room among thirty active unpublished drafts; archives retain
    at most one hundred records per author and family.
    """
    return _set("editorial", params)


@tool()
@safe_tool
def set_progression_experiment_archived(params: ArchiveExperimentIn) -> AuthoringArchiveOut:
    """Archive or restore an owned notebook entry with confirmation and a stable UUID.

    Retains all comparisons, decisions and checkpoints with existing grant checks.
    Revision changes make previous evidence stale; archived entries are read-only.
    Replay reports current state and its original operation without reapplying it.
    Restore requires room among twenty active entries; archives retain at most100.
    """
    return _set("experiment", params)
