"""Audit C1: Chore is per-family content.

Pre-fix the Chore model had no ``family`` FK and ``ChoreViewSet.get_queryset``
returned every household's chores to every parent. A child in family A
could complete a chore authored in family B.

This file pins the family FK + queryset filter against cross-family
probes — both at the REST surface and the MCP tool surface.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from config.tests.factories import make_family


class _TwoFamilyFixture(TestCase):
    def setUp(self):
        self.fam_a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.fam_b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        # Chores authored in each family.
        self.chore_a = Chore.objects.create(
            title="Take out the trash",
            recurrence="daily",
            assigned_to=self.fam_a.children[0],
            created_by=self.fam_a.parents[0],
            family=self.fam_a.family,
        )
        self.chore_b = Chore.objects.create(
            title="Walk the dog",
            recurrence="daily",
            assigned_to=self.fam_b.children[0],
            created_by=self.fam_b.parents[0],
            family=self.fam_b.family,
        )
        self.client = APIClient()


class ChoreModelFamilyTests(_TwoFamilyFixture):
    def test_each_chore_attached_to_authoring_family(self):
        self.assertEqual(self.chore_a.family, self.fam_a.family)
        self.assertEqual(self.chore_b.family, self.fam_b.family)

    def test_chore_save_auto_attaches_default_family_when_unset(self):
        # Defense-in-depth pattern (matches User / Reward / ProjectTemplate).
        # Tests / fixtures that omit ``family`` should still produce a row
        # rather than IntegrityError.
        from apps.families.models import Family

        chore = Chore.objects.create(
            title="Legacy",
            recurrence="daily",
            created_by=self.fam_a.parents[0],
        )
        default = Family.objects.get(slug="default-family")
        self.assertEqual(chore.family, default)


class ChoreViewSetFamilyScopingTests(_TwoFamilyFixture):
    def test_alpha_parent_sees_only_alpha_chores(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get("/api/chores/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        ids = [row["id"] for row in rows]
        self.assertIn(self.chore_a.id, ids)
        self.assertNotIn(self.chore_b.id, ids)

    def test_alpha_kid_sees_only_alpha_chores(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.get("/api/chores/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        ids = [row["id"] for row in rows]
        self.assertIn(self.chore_a.id, ids)
        self.assertNotIn(self.chore_b.id, ids)

    def test_alpha_kid_cannot_complete_bravo_chore(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.post(f"/api/chores/{self.chore_b.id}/complete/")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(
            ChoreCompletion.objects.filter(chore=self.chore_b).exists(),
        )

    def test_alpha_parent_cannot_update_bravo_chore(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.patch(
            f"/api/chores/{self.chore_b.id}/",
            {"title": "Compromised"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.chore_b.refresh_from_db()
        self.assertEqual(self.chore_b.title, "Walk the dog")

    def test_alpha_parent_cannot_delete_bravo_chore(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.delete(f"/api/chores/{self.chore_b.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Chore.objects.filter(pk=self.chore_b.id).exists())

    def test_alpha_parent_create_stamps_alpha_family(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.post(
            "/api/chores/",
            {
                "title": "New chore",
                "reward_amount": "1.50",
                "coin_reward": 5,
                "recurrence": "daily",
            },
            format="json",
        )
        self.assertIn(resp.status_code, (200, 201), resp.content)
        new = Chore.objects.get(title="New chore")
        self.assertEqual(new.family, self.fam_a.family)

    def test_alpha_kid_proposal_stamps_alpha_family(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.post(
            "/api/chores/",
            {
                "title": "Kid proposal",
                "recurrence": "daily",
            },
            format="json",
        )
        self.assertIn(resp.status_code, (200, 201), resp.content)
        new = Chore.objects.get(title="Kid proposal")
        self.assertEqual(new.family, self.fam_a.family)
        self.assertTrue(new.pending_parent_review)


class MCPChoreFamilyScopingTests(TestCase):
    """Audit C1: MCP chore tools must family-scope. Mirrors the REST tests
    but goes through the MCP tool layer so the fix at both surfaces is
    pinned by tests.
    """

    def setUp(self):
        self.a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.chore_a = Chore.objects.create(
            title="Trash A", recurrence="daily",
            assigned_to=self.a.children[0],
            created_by=self.a.parents[0],
            family=self.a.family,
        )
        self.chore_b = Chore.objects.create(
            title="Trash B", recurrence="daily",
            assigned_to=self.b.children[0],
            created_by=self.b.parents[0],
            family=self.b.family,
        )

    def test_list_chores_parent_sees_only_own_family(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.schemas import ListChoresIn
        from apps.mcp_server.tools.chores import list_chores

        with override_user(self.a.parents[0]):
            result = list_chores(ListChoresIn())
        ids = {c["id"] for c in result["chores"]}
        self.assertIn(self.chore_a.id, ids)
        self.assertNotIn(self.chore_b.id, ids)

    def test_get_chore_cross_family_404(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import GetChoreIn
        from apps.mcp_server.tools.chores import get_chore

        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                get_chore(GetChoreIn(chore_id=self.chore_b.id))

    def test_update_chore_cross_family_404(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import UpdateChoreIn
        from apps.mcp_server.tools.chores import update_chore

        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                update_chore(UpdateChoreIn(
                    chore_id=self.chore_b.id, title="hax",
                ))

    def test_complete_chore_cross_family_404(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import CompleteChoreIn
        from apps.mcp_server.tools.chores import complete_chore

        with override_user(self.a.children[0]):
            with self.assertRaises(MCPNotFoundError):
                complete_chore(CompleteChoreIn(chore_id=self.chore_b.id))

    def test_create_chore_stamps_caller_family(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.schemas import CreateChoreIn
        from apps.mcp_server.tools.chores import create_chore

        with override_user(self.a.parents[0]):
            result = create_chore(CreateChoreIn(
                title="MCP-created",
                reward_amount=Decimal("0.50"),
                coin_reward=2,
                recurrence="daily",
            ))
        new = Chore.objects.get(pk=result["id"])
        self.assertEqual(new.family, self.a.family)
