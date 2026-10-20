"""Reviewed Lorebook copy and affirmation authoring, without reward-rule edits."""
import json

from apps.rpg.content import editorial
from apps.rpg.content.loader import ContentPackError

from ..context import get_current_user, require_staff_parent
from ..editorial_schemas import (
    CreateEditorialDraftIn, EditorialCatalogResult, EditorialDraftIn, EditorialDraftPage,
    EditorialDraftResult, EditorialRevisionIn, EditorialSectionIn, ListEditorialDraftsIn,
    PublishEditorialDraftIn, SaveEditorialDraftIn,
)
from ..errors import MCPValidationError, safe_tool
from ..server import tool


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ContentPackError as exc:
        raise MCPValidationError(str(exc)) from None


@tool()
@safe_tool
def list_editorial_content(params: EditorialSectionIn) -> EditorialCatalogResult:
    """Read global Lorebook/affirmation copy, including retired affirmation IDs.

    No learner discovery, journal, gratitude text or household state is read.
    Lorebook mechanics text explains installed behavior; it does not configure it.
    """
    get_current_user()
    return {"section": params.section, "entries": _call(editorial.editorial_catalog, params.section)}


@tool()
@safe_tool
def create_editorial_draft(params: CreateEditorialDraftIn) -> EditorialDraftResult:
    """Create a private textual draft; this publishes nothing."""
    return _call(editorial.create_editorial_draft, require_staff_parent(), params.section, params.name)


@tool()
@safe_tool
def list_editorial_drafts(params: ListEditorialDraftsIn) -> EditorialDraftPage:
    """Read only the acting author's family-bound editorial drafts."""
    return _call(editorial.list_editorial_drafts, require_staff_parent(), after=params.after, limit=params.limit)


@tool()
@safe_tool
def get_editorial_draft(params: EditorialDraftIn) -> EditorialDraftResult:
    """Read one draft and its exact saved preview/publication receipt."""
    return _call(editorial.get_editorial_draft, require_staff_parent(), params.draft_id)


@tool()
@safe_tool
def save_editorial_draft(params: SaveEditorialDraftIn) -> EditorialDraftResult:
    """Save a revisioned copy edit, invalidating the previous preview.

    Lorebook accepts existing slugs and title/audience_title/summary/kid_voice/
    mechanics text. Affirmations accept text (single line, <=90 chars), tone and
    is_active. Retiring an affirmation preserves its slug and historical reads.
    Trial handlers, unlock conditions, economy flags and rewards are source-only.
    """
    changes = [change.model_dump() for change in params.changes]
    if len(json.dumps(changes, ensure_ascii=False).encode()) > 200000:
        raise MCPValidationError("Editorial changes exceed 200 KB; split the draft.")
    return _call(editorial.save_editorial_draft, require_staff_parent(), params.draft_id, params.revision, changes)


@tool()
@safe_tool
def preview_editorial_draft(params: EditorialRevisionIn) -> EditorialDraftResult:
    """Validate exact textual changes and save a preview valid for 30 minutes."""
    return _call(editorial.preview_editorial_draft, require_staff_parent(), params.draft_id, params.revision)


@tool()
@safe_tool
def publish_editorial_draft(params: PublishEditorialDraftIn) -> EditorialDraftResult:
    """Publish the exact reviewed revision after explicit transport confirmation.

    Source/catalog changes or expiry require a fresh preview. Exact retries
    return the publication receipt; no files, assets or reward rules are changed.
    """
    return _call(editorial.publish_editorial_draft, require_staff_parent(), params.draft_id,
                 params.revision, params.preview_id, params.content_digest)
