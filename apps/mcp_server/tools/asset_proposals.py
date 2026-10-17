"""Proposal-only handoff to an external asset pipeline; never generates art."""
import hashlib
import json

from django.db import transaction

from ..asset_schemas import (
    GetAssetProposalIn, InspectAssetProposalIn, ListAssetProposalsIn, ProposeAssetIn,
    RecordAssetDeliveryIn, ReviewAssetProposalIn, UpdateAssetProposalIn,
)
from ..context import get_in_family, require_staff_parent
from ..errors import MCPValidationError, safe_tool
from ..models import AssetProposal, AssetProposalEvent
from ..server import tool


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _proposal(proposal_id, actor, *, lock=False):
    row = get_in_family(AssetProposal, proposal_id, actor=actor, family_path="family")
    if lock:
        row = AssetProposal.objects.select_for_update().get(pk=row.pk, family=actor.family)
    return row


def _event(row, actor, action, details):
    AssetProposalEvent.objects.create(proposal=row, actor=actor, revision=row.revision, action=action, details=details)


def _shape(row, *, events=False, after_event_id=0, event_limit=25):
    result = {
        "id": row.pk, "revision": row.revision, "status": row.status,
        "brief": row.brief, "brief_digest": row.brief_digest,
        "delivery": row.delivery, "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "publication_authority": "proposal_only", "catalog_enabled": False,
        "delivery_verified": False,
    }
    if events:
        history = list(row.events.filter(pk__gt=after_event_id).order_by("id")[:event_limit + 1])
        more = len(history) > event_limit
        history = history[:event_limit]
        result["events"] = [{
            "id": event.pk, "revision": event.revision, "actor_id": event.actor_id,
            "created_at": event.created_at.isoformat(), "action": event.action,
            "details": {key: value for key, value in event.details.items() if key != "brief"},
        } for event in history]
        result["event_total"] = row.events.count()
        result["next_after_event_id"] = history[-1].pk if more else None
    return result


def _check_revision(row, revision):
    if row.revision != revision:
        raise MCPValidationError("Proposal changed. Fetch its current revision and review it again.")


@tool()
@safe_tool
def propose_asset(params: ProposeAssetIn) -> dict:
    """Save an asset brief with explicit intended uses and technical acceptance criteria.

    Duplicate request IDs with identical original input return the saved proposal.
    No provider call, external job, catalog change, reward or upload occurs.
    """
    actor = require_staff_parent()
    brief = params.brief.model_dump(mode="json")
    digest = _digest(brief)
    with transaction.atomic():
        # Serialize same-family request retries even when no proposal row exists.
        type(actor.family).objects.select_for_update().get(pk=actor.family_id)
        row, created = AssetProposal.objects.get_or_create(
            family=actor.family, request_id=params.request_id,
            defaults={"created_by": actor, "brief": brief, "brief_digest": digest, "request_digest": digest},
        )
        if row.request_digest != digest:
            raise MCPValidationError("This request_id was already used for a different asset brief.")
        if created:
            _event(row, actor, "proposed", {"brief": brief, "brief_digest": digest})
    return _shape(row)


@tool()
@safe_tool
def list_asset_proposals(params: ListAssetProposalsIn) -> dict:
    """List the caller family's asset briefs with stable ID pagination."""
    actor = require_staff_parent()
    qs = AssetProposal.objects.filter(family=actor.family, pk__gt=params.after_id).order_by("pk")
    if params.status:
        qs = qs.filter(status=params.status)
    rows = list(qs[:params.limit + 1])
    has_more = len(rows) > params.limit
    rows = rows[:params.limit]
    return {"proposals": [_shape(row) for row in rows], "next_after_id": rows[-1].pk if has_more else None}


@tool()
@safe_tool
def get_asset_proposal(params: InspectAssetProposalIn) -> dict:
    """Inspect a family proposal with paginated history summaries and brief digests."""
    return _shape(_proposal(params.proposal_id, require_staff_parent()), events=True,
                  after_event_id=getattr(params, "after_event_id", 0), event_limit=getattr(params, "event_limit", 25))


@tool()
@safe_tool
def update_asset_proposal(params: UpdateAssetProposalIn) -> dict:
    """Replace a brief at an expected revision; changes reset its ready review."""
    actor = require_staff_parent()
    with transaction.atomic():
        row = _proposal(params.proposal_id, actor, lock=True)
        _check_revision(row, params.expected_revision)
        if row.status in {AssetProposal.Status.CANCELLED, AssetProposal.Status.DELIVERED}:
            raise MCPValidationError("Create a new proposal for cancelled or delivered work.")
        brief = params.brief.model_dump(mode="json")
        digest = _digest(brief)
        if row.brief_digest == digest:
            return _shape(row)
        row.brief, row.brief_digest = brief, digest
        row.status = AssetProposal.Status.PROPOSED
        row.revision += 1
        row.save()
        _event(row, actor, "revised", {"brief": brief, "brief_digest": digest})
    return _shape(row)


@tool()
@safe_tool
def review_asset_proposal(params: ReviewAssetProposalIn) -> dict:
    """Mark a reviewed exact brief ready for external production, or cancel it.

    Ready means its brief can be exported; it grants no artwork/license/runtime approval.
    """
    actor = require_staff_parent()
    with transaction.atomic():
        row = _proposal(params.proposal_id, actor, lock=True)
        _check_revision(row, params.expected_revision)
        if row.status in {AssetProposal.Status.DELIVERED, AssetProposal.Status.CANCELLED}:
            raise MCPValidationError("This proposal is closed.")
        row.status = params.decision
        row.revision += 1
        row.save()
        _event(row, actor, "reviewed", {"decision": params.decision, "notes": params.notes, "brief_digest": row.brief_digest})
    return _shape(row)


@tool()
@safe_tool
def export_asset_proposal(params: GetAssetProposalIn) -> dict:
    """Return a reviewed versioned JSON production brief for an external pipeline.

    This is a read-only export; it never contacts or starts the external pipeline.
    """
    row = _proposal(params.proposal_id, require_staff_parent())
    if row.status != AssetProposal.Status.READY:
        raise MCPValidationError("Review the current brief as ready before exporting it.")
    return {
        "contract": "abby.asset-proposal", "contract_version": 1,
        "proposal_id": row.pk, "revision": row.revision,
        "brief_digest": row.brief_digest, "brief": row.brief,
        "publication_authority": "proposal_only",
        "delivery_instructions": "Return an opaque artifact ID and SHA-256 for separate inspection. Artwork review, supported-art bindings and runtime publication remain separate approvals.",
    }


@tool()
@safe_tool
def record_asset_delivery(params: RecordAssetDeliveryIn) -> dict:
    """Record an external artifact claim without downloading, approving or publishing it."""
    actor = require_staff_parent()
    with transaction.atomic():
        row = _proposal(params.proposal_id, actor, lock=True)
        _check_revision(row, params.expected_revision)
        if row.status != AssetProposal.Status.READY:
            raise MCPValidationError("Only a ready brief can receive an external delivery record.")
        row.delivery = {"artifact_id": params.artifact_id, "sha256": params.sha256, "notes": params.notes, "brief_digest": row.brief_digest}
        row.status = AssetProposal.Status.DELIVERED
        row.revision += 1
        row.save()
        _event(row, actor, "delivery_recorded", row.delivery)
    return _shape(row)
