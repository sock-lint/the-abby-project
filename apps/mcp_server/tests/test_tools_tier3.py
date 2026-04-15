"""Tests for Tier-3 MCP tools: update_child, collaborators, savings update/delete, portfolio media."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AddCollaboratorIn,
    CreateSavingsGoalIn,
    DeleteSavingsGoalIn,
    ListPortfolioMediaIn,
    RemoveCollaboratorIn,
    UpdateChildIn,
    UpdateSavingsGoalIn,
)
from apps.mcp_server.tools import portfolio as pf
from apps.mcp_server.tools import projects as project_tools
from apps.mcp_server.tools import savings as sv
from apps.mcp_server.tools import users as user_tools
from apps.accounts.models import User
from apps.projects.models import (
    Project,
    ProjectCollaborator,
    SavingsGoal,
)


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
            hourly_rate=Decimal("5.00"),
        )


class UpdateChildTests(_Base):
    def test_update_hourly_rate(self) -> None:
        with override_user(self.parent):
            user_tools.update_child(UpdateChildIn(
                user_id=self.child.id,
                hourly_rate=Decimal("7.50"),
            ))
        self.child.refresh_from_db()
        self.assertEqual(self.child.hourly_rate, Decimal("7.50"))

    def test_update_display_name(self) -> None:
        with override_user(self.parent):
            user_tools.update_child(UpdateChildIn(
                user_id=self.child.id, display_name="Abby",
            ))
        self.child.refresh_from_db()
        self.assertEqual(self.child.display_name, "Abby")

    def test_empty_update_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            user_tools.update_child(UpdateChildIn(user_id=self.child.id))

    def test_child_cannot_update(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            user_tools.update_child(UpdateChildIn(
                user_id=self.child.id, hourly_rate=Decimal("100"),
            ))

    def test_update_non_child_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            user_tools.update_child(UpdateChildIn(
                user_id=self.parent.id, display_name="self",
            ))


class CollaboratorTests(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.other_child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        self.project = Project.objects.create(
            title="T", created_by=self.parent, assigned_to=self.child,
        )

    def test_add_collaborator(self) -> None:
        with override_user(self.parent):
            r = project_tools.add_collaborator(AddCollaboratorIn(
                project_id=self.project.id,
                user_id=self.other_child.id,
                pay_split_percent=30,
            ))
        self.assertEqual(r["user_id"], self.other_child.id)
        self.assertEqual(r["pay_split_percent"], 30)

    def test_cannot_add_primary_assignee_as_collaborator(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.add_collaborator(AddCollaboratorIn(
                project_id=self.project.id,
                user_id=self.child.id,
            ))

    def test_duplicate_collaborator_rejected(self) -> None:
        ProjectCollaborator.objects.create(
            project=self.project, user=self.other_child,
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.add_collaborator(AddCollaboratorIn(
                project_id=self.project.id,
                user_id=self.other_child.id,
            ))

    def test_remove_collaborator(self) -> None:
        ProjectCollaborator.objects.create(
            project=self.project, user=self.other_child,
        )
        with override_user(self.parent):
            r = project_tools.remove_collaborator(RemoveCollaboratorIn(
                project_id=self.project.id,
                user_id=self.other_child.id,
            ))
        self.assertTrue(r["deleted"])

    def test_remove_nonexistent_collaborator(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            project_tools.remove_collaborator(RemoveCollaboratorIn(
                project_id=self.project.id,
                user_id=self.other_child.id,
            ))


class SavingsGoalUpdateDeleteTests(_Base):
    def test_update_own_goal(self) -> None:
        goal = SavingsGoal.objects.create(
            user=self.child, title="orig", target_amount=Decimal("100"),
        )
        with override_user(self.child):
            sv.update_savings_goal(UpdateSavingsGoalIn(
                goal_id=goal.id, title="new",
            ))
        goal.refresh_from_db()
        self.assertEqual(goal.title, "new")

    def test_cannot_update_others_goal(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        goal = SavingsGoal.objects.create(
            user=other, title="t", target_amount=Decimal("100"),
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            sv.update_savings_goal(UpdateSavingsGoalIn(
                goal_id=goal.id, title="hacked",
            ))

    def test_delete_own_goal(self) -> None:
        goal = SavingsGoal.objects.create(
            user=self.child, title="t", target_amount=Decimal("100"),
        )
        with override_user(self.child):
            r = sv.delete_savings_goal(
                DeleteSavingsGoalIn(goal_id=goal.id),
            )
        self.assertTrue(r["deleted"])


class PortfolioMediaTests(_Base):
    def test_empty_portfolio(self) -> None:
        with override_user(self.child):
            r = pf.list_portfolio_media(ListPortfolioMediaIn())
        self.assertEqual(r["count"], 0)

    def test_child_sees_only_own(self) -> None:
        from apps.portfolio.models import ProjectPhoto
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        mine = Project.objects.create(
            title="M", created_by=self.parent, assigned_to=self.child,
        )
        theirs = Project.objects.create(
            title="T", created_by=self.parent, assigned_to=other,
        )
        ProjectPhoto.objects.create(project=mine, user=self.child)
        ProjectPhoto.objects.create(project=theirs, user=other)
        with override_user(self.child):
            r = pf.list_portfolio_media(ListPortfolioMediaIn())
        # Only mine visible
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["media"][0]["project_id"], mine.id)
