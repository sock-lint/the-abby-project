"""Tests for the list_children / get_user tools."""
from __future__ import annotations

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import GetUserIn, ListChildrenIn
from apps.mcp_server.tools import users as user_tools
from apps.projects.models import User


class ListChildrenTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child1 = User.objects.create_user(
            username="c1", password="pw", role="child",
        )
        self.child2 = User.objects.create_user(
            username="c2", password="pw", role="child",
        )

    def test_parent_sees_all_children(self) -> None:
        with override_user(self.parent):
            result = user_tools.list_children(ListChildrenIn())
        self.assertEqual(len(result["children"]), 2)

    def test_child_cannot_list_children(self) -> None:
        with override_user(self.child1), self.assertRaises(MCPPermissionDenied):
            user_tools.list_children(ListChildrenIn())


class GetUserTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.other_child = User.objects.create_user(
            username="o", password="pw", role="child",
        )

    def test_child_can_get_self(self) -> None:
        with override_user(self.child):
            result = user_tools.get_user(GetUserIn())
        self.assertEqual(result["username"], "c")

    def test_child_cannot_get_another_child(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            user_tools.get_user(GetUserIn(user_id=self.other_child.id))

    def test_parent_can_get_any_user(self) -> None:
        with override_user(self.parent):
            result = user_tools.get_user(GetUserIn(user_id=self.child.id))
        self.assertEqual(result["id"], self.child.id)
