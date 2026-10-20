"""Complete, scoped project/payment history over the registered MCP adapter."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone
from mcp.server.fastmcp.exceptions import ToolError

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from config.tests.factories import make_family


class HistoryPaginationTests(TransactionTestCase):
    def setUp(self):
        self.a = make_family(
            "History A", parents=[{"username": "history-ap", "is_staff": True}, {"username": "history-coparent", "is_staff": True}],
            children=[{"username": "history-ac"}, {"username": "history-sibling"}],
        )
        self.b = make_family(
            "History B", parents=[{"username": "history-bp", "is_staff": True}],
            children=[{"username": "history-bc"}],
        )
        self.parent, self.child = self.a.parents[0], self.a.children[0]

    def invoke(self, name, params, *, actor=None):
        async def run():
            with override_user(actor or self.parent, scopes=frozenset({"mcp:read"})):
                try:
                    return await mcp._tool_manager.get_tool(name).run({"params": params})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def projects(self, count, *, child=None, **extra):
        rows = Project.objects.bulk_create([
            Project(title=f"Synthetic project {n}", assigned_to=child or self.child, created_by=self.parent, **extra)
            for n in range(count)
        ])
        Project.objects.filter(pk__in=[row.pk for row in rows]).update(created_at=timezone.now() - timedelta(days=1))
        return rows

    def payments(self, count, *, child=None, entry_type="adjustment"):
        rows = PaymentLedger.objects.bulk_create([
            PaymentLedger(user=child or self.child, amount=Decimal("1.00"), entry_type=entry_type, created_by=self.parent)
            for _ in range(count)
        ])
        PaymentLedger.objects.filter(pk__in=[row.pk for row in rows]).update(created_at=timezone.now() - timedelta(days=1))
        return rows

    def traversal(self, name, params, result_key):
        ids, cursor = [], None
        while True:
            result = self.invoke(name, {**params, **({"cursor": cursor} if cursor else {})})
            self.assertEqual(result["has_more"], result["next_cursor"] is not None)
            ids.extend(row["id"] for row in result[result_key])
            if name == "list_projects":
                self.assertEqual(result["count"], len(result[result_key]))
            if result["next_cursor"] is None:
                return ids, result
            cursor = result["next_cursor"]
            self.assertLess(len(ids), 1000, "Pagination must terminate without repeating a page")

    def test_projects_traverse_past_maximum_page_size_and_tied_timestamps(self):
        rows = self.projects(205)
        self.projects(3, child=self.b.children[0])
        ids, result = self.traversal("list_projects", {"limit": 200}, "projects")
        self.assertEqual(ids, sorted((row.pk for row in rows), reverse=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(result["total"], 205)

    def test_payments_traverse_past_maximum_page_size_and_tied_timestamps(self):
        rows = self.payments(505)
        self.payments(3, child=self.b.children[0])
        ids, result = self.traversal("list_payment_ledger", {"user_id": self.child.pk, "limit": 500}, "entries")
        self.assertEqual(ids, sorted((row.pk for row in rows), reverse=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(result["total"], 505)

    def test_new_rows_do_not_enter_existing_page_sequence(self):
        for name, create, key, params in (
            ("list_projects", self.projects, "projects", {}),
            ("list_payment_ledger", self.payments, "entries", {"user_id": self.child.pk}),
        ):
            rows = create(3)
            first = self.invoke(name, {**params, "limit": 1})
            inserted = create(1)[0]
            second = self.invoke(name, {**params, "limit": 2, "cursor": first["next_cursor"]})
            with self.subTest(tool=name):
                self.assertEqual([r["id"] for r in first[key] + second[key]], sorted((row.pk for row in rows), reverse=True))
                self.assertNotIn(inserted.pk, [r["id"] for r in second[key]])
                self.assertEqual(second["total"], 3)
                self.assertFalse(second["has_more"])

    def test_tampered_expired_actor_family_and_tool_cursors_are_rejected(self):
        self.projects(2)
        self.payments(2)
        first = self.invoke("list_projects", {"limit": 1})
        cursor = first["next_cursor"]
        for token in ("not-a-cursor", cursor + "tampered"):
            with self.subTest(token=token), self.assertRaisesRegex(ToolError, "cursor"):
                self.invoke("list_projects", {"cursor": token})
        for actor in (self.a.parents[1], self.b.parents[0]):
            with self.subTest(actor=actor.pk), self.assertRaisesRegex(ToolError, "cursor"):
                self.invoke("list_projects", {"cursor": cursor}, actor=actor)
        actor = self.a.parents[0]
        actor.family = self.b.family
        with self.assertRaisesRegex(ToolError, "cursor"):
            self.invoke("list_projects", {"cursor": cursor}, actor=actor)
        actor.family = self.a.family
        with self.assertRaisesRegex(ToolError, "cursor"):
            self.invoke("list_payment_ledger", {"user_id": self.child.pk, "cursor": cursor})
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 86402):
            with self.assertRaisesRegex(ToolError, "cursor"):
                self.invoke("list_projects", {"cursor": cursor})

    def test_project_filters_remain_in_effect_and_cannot_change_with_cursor(self):
        rows = self.projects(3, status="active")
        self.projects(2, status="completed")
        first = self.invoke("list_projects", {"status": "active", "limit": 1})
        for change in ({"status": "completed"}, {"status": "active", "assigned_to_id": self.child.pk}):
            with self.subTest(change=change), self.assertRaisesRegex(ToolError, "cursor"):
                self.invoke("list_projects", {**change, "cursor": first["next_cursor"]})
        ids, result = self.traversal("list_projects", {"status": "active", "limit": 2}, "projects")
        self.assertEqual(set(ids), {row.pk for row in rows})
        self.assertEqual(result["total"], 3)

    def test_payment_filters_timezone_and_target_cannot_change_with_cursor(self):
        self.payments(3)
        self.payments(2, entry_type="hourly")
        params = {"user_id": self.child.pk, "entry_type": "adjustment"}
        first = self.invoke("list_payment_ledger", {**params, "limit": 1})
        for change in ({"entry_type": "hourly"}, {"since": "2026-01-01"}, {"user_id": self.a.children[1].pk}):
            with self.subTest(change=change), self.assertRaisesRegex(ToolError, "cursor"):
                self.invoke("list_payment_ledger", {**params, **change, "cursor": first["next_cursor"]})
        with timezone.override("UTC"), self.assertRaisesRegex(ToolError, "cursor"):
            self.invoke("list_payment_ledger", {**params, "cursor": first["next_cursor"]})
        ids, result = self.traversal("list_payment_ledger", {**params, "limit": 2}, "entries")
        self.assertEqual(len(ids), 3)
        self.assertEqual(result["total"], 3)

    def test_empty_histories_and_foreign_queries_do_not_leak_counts(self):
        self.projects(3, child=self.b.children[0])
        self.payments(3, child=self.b.children[0])
        for params in ({}, {"assigned_to_id": self.b.children[0].pk}, {"assigned_to_id": 999999}):
            result = self.invoke("list_projects", params)
            self.assertEqual(result, {"projects": [], "count": 0, "total": 0, "has_more": False, "next_cursor": None})
        for user_id in (self.b.children[0].pk, 999999):
            with self.subTest(user_id=user_id), self.assertRaisesRegex(ToolError, "not found"):
                self.invoke("list_payment_ledger", {"user_id": user_id})
        result = self.invoke("list_payment_ledger", {"user_id": self.child.pk})
        self.assertEqual(result, {"entries": [], "total": 0, "has_more": False, "next_cursor": None})

    def test_child_histories_remain_self_scoped(self):
        own = self.projects(3)
        self.projects(2, child=self.a.children[1])
        self.payments(3)
        self.payments(2, child=self.a.children[1])
        result = self.invoke("list_projects", {"assigned_to_id": self.a.children[1].pk, "limit": 2}, actor=self.child)
        self.assertEqual(result["total"], len(own))
        result = self.invoke("list_payment_ledger", {}, actor=self.child)
        self.assertEqual(result["total"], 3)
        with self.assertRaisesRegex(ToolError, "own data"):
            self.invoke("list_payment_ledger", {"user_id": self.a.children[1].pk}, actor=self.child)
