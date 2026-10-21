"""Exercise homework reads through the registered MCP adapter across families."""
from datetime import date

from asgiref.sync import async_to_sync, sync_to_async
from django.db import connections
from django.test import TransactionTestCase
from mcp.server.fastmcp.exceptions import ToolError

from apps.homework.models import HomeworkAssignment
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from config.tests.factories import make_family


class HomeworkReadIsolationTests(TransactionTestCase):
    def setUp(self):
        self.a = make_family(
            "Homework A", parents=[{"username": "homework-ap", "is_staff": True}],
            children=[{"username": "homework-ac"}, {"username": "homework-sibling"}],
        )
        self.b = make_family(
            "Homework B", parents=[{"username": "homework-bp", "is_staff": True}],
            children=[{"username": "homework-bc"}],
        )
        self.own = self.assignment(self.a.children[0], self.a.parents[0], "A notes")
        self.sibling = self.assignment(self.a.children[1], self.a.parents[0], "Sibling notes")
        self.foreign = self.assignment(self.b.children[0], self.b.parents[0], "B notes")

    def assignment(self, child, parent, notes):
        return HomeworkAssignment.objects.create(
            title="Synthetic homework", notes=notes, subject="math",
            due_date=date(2026, 10, 21), assigned_to=child, created_by=parent,
        )

    def invoke(self, name, params, *, actor=None, scopes=frozenset({"mcp:read"})):
        async def run():
            with override_user(actor or self.a.parents[0], scopes=scopes):
                try:
                    return await mcp._tool_manager.get_tool(name).run({"params": params})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def test_parent_default_list_contains_only_own_family(self):
        result = self.invoke("list_homework", {})
        self.assertEqual({row["id"] for row in result["assignments"]}, {self.own.pk, self.sibling.pk})

    def test_foreign_and_missing_child_filters_reveal_no_homework(self):
        for child_id in (self.b.children[0].pk, 999999):
            with self.subTest(child_id=child_id):
                result = self.invoke("list_homework", {"assigned_to_id": child_id})
                self.assertEqual(result["assignments"], [])

    def test_foreign_and_missing_detail_return_not_found(self):
        for assignment_id in (self.foreign.pk, 999999):
            with self.subTest(assignment_id=assignment_id), self.assertRaisesRegex(ToolError, "not found"):
                self.invoke("get_homework", {"assignment_id": assignment_id})

    def test_parent_can_read_own_and_sibling_detail(self):
        for row in (self.own, self.sibling):
            with self.subTest(assignment_id=row.pk):
                self.assertEqual(self.invoke("get_homework", {"assignment_id": row.pk})["notes"], row.notes)

    def test_child_can_read_only_self_even_with_another_child_filter(self):
        child = self.a.children[0]
        result = self.invoke("list_homework", {"assigned_to_id": self.a.children[1].pk}, actor=child)
        self.assertEqual([row["id"] for row in result["assignments"]], [self.own.pk])
        self.assertEqual(self.invoke("get_homework", {"assignment_id": self.own.pk}, actor=child)["id"], self.own.pk)
        for row in (self.sibling, self.foreign):
            with self.subTest(assignment_id=row.pk), self.assertRaisesRegex(ToolError, "not found"):
                self.invoke("get_homework", {"assignment_id": row.pk}, actor=child)

    def test_inactive_homework_is_hidden_on_list_and_detail(self):
        self.own.is_active = False
        self.own.save(update_fields=["is_active"])
        result = self.invoke("list_homework", {})
        self.assertNotIn(self.own.pk, [row["id"] for row in result["assignments"]])
        with self.assertRaisesRegex(ToolError, "not found"):
            self.invoke("get_homework", {"assignment_id": self.own.pk})

    def test_familyless_parent_fails_closed(self):
        actor = self.a.parents[0]
        actor.family = None
        self.assertEqual(self.invoke("list_homework", {}, actor=actor)["assignments"], [])
        with self.assertRaisesRegex(ToolError, "not found"):
            self.invoke("get_homework", {"assignment_id": self.own.pk}, actor=actor)

    def test_catalog_scope_cannot_read_homework(self):
        with self.assertRaisesRegex(ToolError, "permission"):
            self.invoke("get_homework", {"assignment_id": self.own.pk}, scopes=frozenset({"mcp:catalog"}))
