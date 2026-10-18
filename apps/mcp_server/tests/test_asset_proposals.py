"""External asset handoffs are scoped, revisioned proposals, not runtime writes."""
from copy import deepcopy
from uuid import uuid4

from django.test import TestCase
from pydantic import ValidationError

from config.tests.factories import make_family
from apps.mcp_server.asset_schemas import (
    GetAssetProposalIn, InspectAssetProposalIn, ListAssetProposalsIn, ProposeAssetIn,
    RecordAssetDeliveryIn, ReviewAssetProposalIn, UpdateAssetProposalIn,
)
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.models import AssetProposal, AssetProposalEvent
from apps.mcp_server.tools import asset_proposals as tools
from apps.rpg.models import ItemDefinition, SpriteAsset, UserInventory
from apps.rewards.models import CoinLedger


def example_brief():
    return {
        "key": "reading-trail-marker", "title": "Reading trail marker", "kind": "icon",
        "creative_brief": "A friendly open book on a woodland trail sign.",
        "rationale": "Distinguish a reading goal from an earned permanent badge.",
        "uses": [{"surface": "challenges", "content_ref": "proposed:reading-trail", "placement": "Challenge card icon",
                  "player_purpose": "Recognize a reading challenge", "integration_notes": "Bind approved PNG to future challenge card; awards remain server-owned."}],
        "requirements": {"formats": ["png"], "width_px": 256, "height_px": 256, "transparent_background": True, "max_file_bytes": 200000},
        "acceptance_criteria": ["Legible at 32px", "No text embedded"],
        "license_requirements": "Original or licensed artwork with documented runtime rights.",
    }


class AssetProposalTests(TestCase):
    def setUp(self):
        home = make_family(parents=[{"username": "asset-author", "is_staff": True}], children=[{"username": "asset-child"}])
        other = make_family(name="Other", parents=[{"username": "other-author", "is_staff": True}])
        self.parent, self.child, self.other = home.parents[0], home.children[0], other.parents[0]
        self.context = override_user(self.parent)
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def create(self, request_id=None):
        return tools.propose_asset(ProposeAssetIn(request_id=request_id or uuid4(), brief=example_brief()))

    def ready(self):
        row = self.create()
        return tools.review_asset_proposal(ReviewAssetProposalIn(proposal_id=row["id"], expected_revision=row["revision"], decision="ready", notes="Brief reviewed for production handoff."))

    def test_request_retries_return_same_proposal_but_changed_input_conflicts(self):
        key = uuid4()
        first, again = self.create(key), self.create(key)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(AssetProposalEvent.objects.count(), 1)
        changed = example_brief()
        changed["title"] = "Different"
        with self.assertRaises(MCPValidationError):
            tools.propose_asset(ProposeAssetIn(request_id=key, brief=changed))
        with override_user(self.other):
            foreign = self.create(key)
            self.assertNotEqual(foreign["id"], first["id"])

    def test_reads_and_exports_never_create_game_state_or_claim_asset_approval(self):
        row = self.ready()
        before = [model.objects.count() for model in (CoinLedger, ItemDefinition, UserInventory, SpriteAsset, AssetProposalEvent)]
        exported = tools.export_asset_proposal(GetAssetProposalIn(proposal_id=row["id"]))
        self.assertEqual(exported["contract_version"], 1)
        self.assertEqual(exported["brief_digest"], row["brief_digest"])
        tools.get_asset_proposal(GetAssetProposalIn(proposal_id=row["id"]))
        tools.list_asset_proposals(ListAssetProposalsIn())
        self.assertEqual(before, [model.objects.count() for model in (CoinLedger, ItemDefinition, UserInventory, SpriteAsset, AssetProposalEvent)])
        self.assertFalse(row["catalog_enabled"])
        self.assertFalse(row["delivery_verified"])

    def test_unreviewed_export_and_stale_revision_are_rejected(self):
        row = self.create()
        with self.assertRaises(MCPValidationError):
            tools.export_asset_proposal(GetAssetProposalIn(proposal_id=row["id"]))
        changed = deepcopy(row["brief"])
        changed["title"] = "Changed title"
        revised = tools.update_asset_proposal(UpdateAssetProposalIn(proposal_id=row["id"], expected_revision=1, brief=changed))
        self.assertEqual(revised["revision"], 2)
        with self.assertRaises(MCPValidationError):
            tools.review_asset_proposal(ReviewAssetProposalIn(proposal_id=row["id"], expected_revision=1, decision="ready", notes="Stale review"))

    def test_editing_ready_brief_requires_fresh_review(self):
        row = self.ready()
        changed = deepcopy(row["brief"])
        changed["requirements"]["width_px"] = 512
        revised = tools.update_asset_proposal(UpdateAssetProposalIn(proposal_id=row["id"], expected_revision=row["revision"], brief=changed))
        self.assertEqual(revised["status"], "proposed")
        with self.assertRaises(MCPValidationError):
            tools.export_asset_proposal(GetAssetProposalIn(proposal_id=row["id"]))
        self.assertEqual(AssetProposalEvent.objects.filter(proposal_id=row["id"]).count(), 3)

    def test_external_delivery_is_only_an_unverified_artifact_reference(self):
        row = self.ready()
        delivered = tools.record_asset_delivery(RecordAssetDeliveryIn(proposal_id=row["id"], expected_revision=row["revision"], artifact_id="pipeline-job-42", sha256="a" * 64, notes="Pipeline reported completion; awaiting actual artwork inspection."))
        self.assertEqual(delivered["status"], "delivered")
        self.assertFalse(delivered["delivery_verified"])
        self.assertFalse(delivered["catalog_enabled"])
        self.assertEqual(SpriteAsset.objects.count(), 0)
        self.assertEqual(ItemDefinition.objects.count(), 0)
        with self.assertRaises(MCPValidationError):
            tools.update_asset_proposal(UpdateAssetProposalIn(proposal_id=row["id"], expected_revision=delivered["revision"], brief=example_brief()))

    def test_private_proposals_cannot_be_read_or_changed_by_another_family(self):
        row = self.create()
        with override_user(self.other):
            self.assertEqual(tools.list_asset_proposals(ListAssetProposalsIn())["proposals"], [])
            for action, params in [
                (tools.get_asset_proposal, GetAssetProposalIn(proposal_id=row["id"])),
                (tools.export_asset_proposal, GetAssetProposalIn(proposal_id=row["id"])),
                (tools.update_asset_proposal, UpdateAssetProposalIn(proposal_id=row["id"], expected_revision=1, brief=example_brief())),
            ]:
                with self.assertRaises(MCPNotFoundError):
                    action(params)
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            self.create()

    def test_list_pagination_is_stable_and_status_filtered(self):
        first = self.create()
        second = self.create()
        page = tools.list_asset_proposals(ListAssetProposalsIn(limit=1))
        self.assertEqual(page["next_after_id"], first["id"])
        page = tools.list_asset_proposals(ListAssetProposalsIn(limit=1, after_id=page["next_after_id"]))
        self.assertEqual(page["proposals"][0]["id"], second["id"])
        self.assertIsNone(page["next_after_id"])
        self.assertEqual(tools.list_asset_proposals(ListAssetProposalsIn(status="delivered"))["proposals"], [])

    def test_revision_history_is_paginated_and_does_not_repeat_large_briefs(self):
        row = self.create()
        for index in range(5):
            brief = example_brief()
            brief["title"] = f"Revision {index}"
            row = tools.update_asset_proposal(UpdateAssetProposalIn(proposal_id=row["id"], expected_revision=row["revision"], brief=brief))
        ids = []
        after = 0
        while True:
            page = tools.get_asset_proposal(InspectAssetProposalIn(proposal_id=row["id"], after_event_id=after, event_limit=2))
            self.assertEqual(page["event_total"], 6)
            self.assertLessEqual(len(page["events"]), 2)
            for event in page["events"]:
                self.assertNotIn("brief", event["details"])
                self.assertIn("brief_digest", event["details"])
            ids.extend(event["id"] for event in page["events"])
            after = page["next_after_event_id"]
            if after is None:
                break
        self.assertEqual(len(set(ids)), 6)

    def test_account_deletion_preserves_proposal_evidence_without_protected_user_references(self):
        row = self.ready()
        proposal = AssetProposal.objects.get(pk=row["id"])
        self.parent.delete()
        proposal.refresh_from_db()
        self.assertIsNone(proposal.created_by_id)
        self.assertEqual(proposal.events.count(), 2)
        self.assertFalse(proposal.events.exclude(actor_id=None).exists())

    def test_arbitrary_provider_controls_approval_claims_and_unbounded_specs_are_rejected(self):
        for key, value in [("approved", True), ("pipeline_url", "https://example.invalid/produce"), ("creative_brief", "x" * 6001)]:
            brief = example_brief()
            brief[key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                ProposeAssetIn(request_id=uuid4(), brief=brief)
        brief = example_brief()
        brief["requirements"]["height_px"] = None
        with self.assertRaises(ValidationError):
            ProposeAssetIn(request_id=uuid4(), brief=brief)
