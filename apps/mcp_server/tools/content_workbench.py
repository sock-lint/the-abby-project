"""MCP access to the native reviewed database workbench and anonymous simulator."""
import math
from contextlib import contextmanager
from types import SimpleNamespace

from apps.rpg.content import workbench
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.workbench_validation import (
    CREATE_ITEM_TYPES, ITEM_BEHAVIOR_FIELDS, ITEM_FIELDS, QUEST_FIELDS, supported_challenge_triggers,
)
from apps.rpg.models import ItemDefinition, RPGContentDraft
from apps.rpg.progression import describe_progression, normalize_config, simulate_progression
from apps.rpg.progression_views import ProgressionSimulationThrottle
from apps.rpg.workbench_views import WorkbenchSimulationThrottle

from ..catalog import catalog_queryset, catalog_row
from ..context import require_staff_parent, reset_current_user, set_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..retries import authorized_household
from ..server import tool
from ..shapes import to_plain
from ..workbench_schemas import (
    ContentDraftComparisonOut, ContentDraftIn, ContentDraftListOut, ContentDraftOut,
    ContentDraftRevisionIn, CreateContentDraftIn, EmptyWorkbenchIn, ListContentDraftsIn,
    ProgressionMetadataOut, ProgressionReportOut, PublishContentDraftIn, SaveContentDraftIn,
    SimulateContentDraftIn, SimulationIn, WorkbenchReferencesIn, WorkbenchReferencesOut,
)


def _actor():
    actor = require_staff_parent()
    if not actor.is_active:
        raise MCPPermissionDenied("Content authoring requires an active staff parent.")
    return actor


@contextmanager
def _authorized_actor():
    # Native services serialize catalog writes; retain the household/member
    # locks first so revocation cannot race a private read or publication replay.
    actor = _actor()
    with authorized_household(actor, actor) as (fresh_actor, _):
        token = set_current_user(fresh_actor)
        try:
            yield require_staff_parent()
        finally:
            reset_current_user(token)


def _call(function, *args, **kwargs):
    try:
        return to_plain(function(*args, **kwargs))
    except ContentAuthorPermissionDenied as error:
        raise MCPPermissionDenied(str(error)) from error
    except (workbench.WorkbenchNotFound, ContentObjectNotFound) as error:
        raise MCPNotFoundError(str(error)) from error
    except workbench.WorkbenchConflict as error:
        raise MCPValidationError(str(error), code="content_workbench_conflict") from error
    except ContentPackError as error:
        raise MCPValidationError(str(error)) from error


def _simulation_quota(actor, throttle_class):
    # Reuse the REST class and cache key: switching transports cannot acquire
    # another allowance for the same expensive anonymous calculation.
    throttle = throttle_class()
    if not throttle.allow_request(SimpleNamespace(user=actor), None):
        seconds = max(1, math.ceil(throttle.wait() or 60))
        raise MCPValidationError(
            f"Simulation rate limit reached. Try again in {seconds} seconds.",
            code="rate_limited", retryable=True,
        )


@tool()
@safe_tool
def get_content_workbench(params: WorkbenchReferencesIn) -> WorkbenchReferencesOut:
    """Read bounded global workbench references and authoring rules without household usage.

    Follow next_after using after for another page. This catalog-only projection
    excludes private drafts, player progress and family shop offer references.
    """
    _actor()
    queryset = catalog_queryset(params.section)
    if params.section == "quests":
        queryset = queryset.filter(created_by__isnull=True)
    rows = list(queryset.filter(pk__gt=params.after).order_by("pk")[:params.limit + 1])
    more = len(rows) > params.limit
    rows = rows[:params.limit]
    return {
        "section": params.section, "results": [to_plain(catalog_row(params.section, row)) for row in rows],
        "total": queryset.count(), "after": params.after, "next_after": rows[-1].pk if more else None,
        "rules": {
            "item_types": sorted(CREATE_ITEM_TYPES), "rarities": list(ItemDefinition.Rarity.values),
            "triggers": supported_challenge_triggers(), "boss_triggers": supported_challenge_triggers("boss"),
            "editable_item_fields": sorted(ITEM_FIELDS), "existing_item_behavior_fields": sorted(ITEM_BEHAVIOR_FIELDS),
            "editable_quest_fields": sorted(QUEST_FIELDS), "max_changes": 100,
            "publication_scope": "Definitions are global; drafts belong to the author and family.",
        },
    }


@tool()
@safe_tool
def list_content_drafts(params: ListContentDraftsIn) -> ContentDraftListOut:
    """Read only this author's same-family draft summaries, in stable UUID order."""
    with _authorized_actor() as actor:
        queryset = RPGContentDraft.objects.filter(actor=actor, family_id=actor.family_id)
        if params.published is not None:
            queryset = queryset.filter(published_at__isnull=not params.published)
        total = queryset.count()
        if params.after is not None:
            queryset = queryset.filter(pk__gt=params.after)
        rows = list(queryset.order_by("pk")[:params.limit + 1])
        more = len(rows) > params.limit
        rows = rows[:params.limit]
        return {"drafts": [{
            "id": str(row.pk), "name": row.name, "revision": row.revision,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "updated_at": row.updated_at.isoformat(),
        } for row in rows], "total": total, "has_more": more, "next_after": str(rows[-1].pk) if more else None}


@tool()
@safe_tool
def get_content_draft(params: ContentDraftIn) -> ContentDraftOut:
    """Read one private database draft, its exact preview and saved evaluation identity."""
    with _authorized_actor() as actor:
        return _call(workbench.get_draft, actor, params.draft_id)


@tool()
@safe_tool
def create_content_draft(params: CreateContentDraftIn) -> ContentDraftOut:
    """Create a private database draft without changing the live catalog."""
    with _authorized_actor() as actor:
        return _call(workbench.create_draft, actor, params.name)


@tool()
@safe_tool
def save_content_draft(params: SaveContentDraftIn) -> ContentDraftOut:
    """Replace draft changes at the expected revision, invalidating its previous review."""
    with _authorized_actor() as actor:
        return _call(
            workbench.save_draft, actor, params.draft_id, params.revision,
            [row.model_dump(mode="json") for row in params.changes], name=params.name,
        )


@tool()
@safe_tool
def preview_content_draft(params: ContentDraftRevisionIn) -> ContentDraftOut:
    """Validate the exact saved revision and review its changes without publishing."""
    with _authorized_actor() as actor:
        return _call(workbench.preview_draft, actor, params.draft_id, params.revision)


@tool()
@safe_tool
def simulate_content_draft(params: SimulateContentDraftIn) -> ContentDraftComparisonOut:
    """Compare the reviewed draft with the baseline using one bounded anonymous scenario.

    Reuses the native five-per-minute author quota. No household accounts,
    inventory, ledger credits or progress are created by either simulation.
    """
    with _authorized_actor() as actor:
        _simulation_quota(actor, WorkbenchSimulationThrottle)
    # Let the native service take fresh authority around snapshot capture and
    # result validation separately. Holding it through computation would also
    # hold the nested catalog locks until both simulations finish.
    return _call(workbench.simulate_draft, actor, params.draft_id, params.revision,
                 params.preview_id, params.config, authorize=_authorized_actor)


@tool()
@safe_tool
def publish_content_draft(params: PublishContentDraftIn) -> ContentDraftOut:
    """Publish the exact reviewed and simulated revision with explicit confirmation.

    Preserves source IDs, earned inventory and accepted promises. A completed
    publication can be replayed; changed revisions, digests or catalog state fail.
    """
    with _authorized_actor() as actor:
        return _call(workbench.publish_draft, actor, params.draft_id, params.revision, params.preview_id, params.content_digest)


@tool()
@safe_tool
def get_progression_lab(params: EmptyWorkbenchIn) -> ProgressionMetadataOut:
    """Read global simulator rules, scenario limits and supported catalog coverage."""
    _actor()
    return _call(describe_progression)


@tool()
@safe_tool
def simulate_progression_scenario(params: SimulationIn) -> ProgressionReportOut:
    """Run a bounded anonymous baseline scenario, including supported 365-day horizons.

    Reuses the native ten-per-minute quota and work-unit budget. This forecasts
    a modeled source subset and creates no household records or reward state.
    """
    actor = _actor()
    config = normalize_config(params.config)
    _simulation_quota(actor, ProgressionSimulationThrottle)
    return _call(simulate_progression, config)
