"""Native and MCP draft computation must run outside catalog transactions."""
from unittest.mock import patch
from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.tools.content_workbench import simulate_content_draft
from apps.mcp_server.workbench_schemas import SimulateContentDraftIn
from apps.quests.models import QuestDefinition
from apps.rpg.content import workbench
from apps.rpg.models import RPGContentDraft
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WorkbenchSimulationTransactionScopeTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.actor = make_family(parents=[{
            "username": "detached-simulation-parent", "is_staff": True,
        }]).parents[0]
        quest = QuestDefinition.objects.create(
            name="Detached simulation source", description="Before review",
            is_system=True, quest_type="collection", target_value=1,
            trigger_filter={"allowed_triggers": ["habit_log"]},
        )
        draft = workbench.create_draft(self.actor, "Review a description")
        draft = workbench.save_draft(self.actor, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": quest.pk, "key": "description",
            "values": {"description": "After review"},
        }])
        self.reviewed = workbench.preview_draft(self.actor, draft["id"], draft["revision"])

    def assert_detached_simulation(self, *_args, **_kwargs):
        self.assertFalse(
            connection.in_atomic_block,
            "Pure simulation still holds the caller's catalog transaction",
        )
        return {"engine_version": "synthetic-detached", "rules_fingerprint": "synthetic-detached"}

    def test_native_computation_releases_snapshot_transaction(self):
        with patch("apps.rpg.progression.simulate_progression", side_effect=self.assert_detached_simulation) as compute:
            result = workbench.simulate_draft(
                self.actor, self.reviewed["id"], self.reviewed["revision"], self.reviewed["preview"]["preview_id"],
            )
        self.assertEqual(compute.call_count, 2)
        self.assertEqual(result["simulation"]["engine_version"], "synthetic-detached")

    def test_mcp_computation_releases_snapshot_and_authorization_transactions(self):
        result, compute = self.invoke()
        self.assertEqual(compute.call_count, 2)
        self.assertEqual(result["simulation"]["engine_version"], "synthetic-detached")

    def invoke(self, during_compute=None):
        params = SimulateContentDraftIn(
            draft_id=self.reviewed["id"], revision=self.reviewed["revision"],
            preview_id=self.reviewed["preview"]["preview_id"],
        )
        def calculate(*args, **kwargs):
            result = self.assert_detached_simulation(*args, **kwargs)
            if during_compute:
                during_compute()
            return result

        with override_user(self.actor), patch(
            "apps.rpg.progression.simulate_progression", side_effect=calculate,
        ) as compute:
            result = simulate_content_draft(params)
        return result, compute

    def assert_no_receipt(self):
        self.assertEqual(RPGContentDraft.objects.get(pk=self.reviewed["id"]).simulation, {})

    def test_permission_revocation_during_computation_rejects_private_result(self):
        with self.assertRaises(MCPPermissionDenied):
            self.invoke(lambda: User.objects.filter(pk=self.actor.pk).update(is_staff=False))
        self.assert_no_receipt()

    def test_family_change_during_computation_rejects_private_result(self):
        family = make_family("Different simulation household").family
        with self.assertRaises(MCPPermissionDenied):
            self.invoke(lambda: User.objects.filter(pk=self.actor.pk).update(family=family))
        self.assert_no_receipt()

    def test_draft_revision_change_during_computation_rejects_receipt(self):
        def revise():
            RPGContentDraft.objects.filter(pk=self.reviewed["id"]).update(revision=self.reviewed["revision"] + 1)
        with self.assertRaisesMessage(MCPValidationError, "revision changed"):
            self.invoke(revise)
        self.assert_no_receipt()

    def test_catalog_change_during_computation_rejects_receipt(self):
        with self.assertRaisesMessage(MCPValidationError, "Catalog state changed"):
            self.invoke(lambda: QuestDefinition.objects.update(description="Changed during computation"))
        self.assert_no_receipt()

    def test_preview_expiry_during_computation_rejects_receipt(self):
        def expire():
            draft = RPGContentDraft.objects.get(pk=self.reviewed["id"])
            type(draft.preview).objects.filter(pk=draft.preview_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaisesMessage(MCPValidationError, "preview expired"):
            self.invoke(expire)
        self.assert_no_receipt()
