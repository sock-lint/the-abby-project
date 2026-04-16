"""Tests for projects.signals — project/milestone status-change side-effects."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectMilestone, User
from apps.rewards.models import CoinLedger


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")


class ProjectStatusChangeTests(_Fixture):
    def _make_project(self, **kwargs):
        defaults = dict(
            title="Test Project", assigned_to=self.child, created_by=self.parent,
            status="draft", difficulty=2, bonus_amount=Decimal("10.00"),
        )
        defaults.update(kwargs)
        return Project.objects.create(**defaults)

    def test_in_progress_sets_started_at(self):
        project = self._make_project(status="draft")
        project.status = "in_progress"
        project.save()
        project.refresh_from_db()
        self.assertIsNotNone(project.started_at)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_posts_project_bonus_payment(self, mock_gl):
        project = self._make_project(status="in_progress")
        project.status = "completed"
        project.save()
        self.assertTrue(
            PaymentLedger.objects.filter(
                user=self.child, entry_type="project_bonus",
            ).exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_bounty_posts_bounty_payout(self, mock_gl):
        project = self._make_project(
            status="in_progress", payment_kind="bounty",
            bonus_amount=Decimal("25.00"),
        )
        project.status = "completed"
        project.save()
        entry = PaymentLedger.objects.filter(
            user=self.child, entry_type="bounty_payout",
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, Decimal("25.00"))

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_awards_coins(self, mock_gl):
        project = self._make_project(status="in_progress")
        project.status = "completed"
        project.save()
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.child, reason=CoinLedger.Reason.PROJECT_BONUS,
            ).exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_sends_notification(self, mock_gl):
        project = self._make_project(status="in_progress")
        project.status = "completed"
        project.save()
        self.assertTrue(
            Notification.objects.filter(
                user=self.child, notification_type="project_approved",
            ).exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_calls_game_loop(self, mock_gl):
        project = self._make_project(status="in_progress")
        project.status = "completed"
        project.save()
        mock_gl.assert_called_once_with(
            self.child, "project_complete",
            {"project_id": project.pk},
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completed_sets_completed_at(self, mock_gl):
        project = self._make_project(status="in_progress")
        project.status = "completed"
        project.save()
        project.refresh_from_db()
        self.assertIsNotNone(project.completed_at)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_no_bonus_skips_payment_ledger(self, mock_gl):
        project = self._make_project(
            status="in_progress", bonus_amount=Decimal("0"),
        )
        project.status = "completed"
        project.save()
        self.assertFalse(
            PaymentLedger.objects.filter(
                user=self.child, entry_type="project_bonus",
            ).exists()
        )

    def test_same_status_no_side_effects(self):
        project = self._make_project(status="in_progress")
        Notification.objects.all().delete()
        project.title = "Renamed"
        project.save()
        self.assertFalse(Notification.objects.exists())


class MilestoneCompletionTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="in_progress", difficulty=1,
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_completing_milestone_sends_notification(self, mock_gl):
        ms = ProjectMilestone.objects.create(
            project=self.project, title="Ch1",
        )
        ms.is_completed = True
        ms.save()
        self.assertTrue(
            Notification.objects.filter(
                user=self.child, notification_type="milestone_completed",
            ).exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_milestone_with_bonus_posts_payment(self, mock_gl):
        ms = ProjectMilestone.objects.create(
            project=self.project, title="Ch1",
            bonus_amount=Decimal("5.00"),
        )
        ms.is_completed = True
        ms.save()
        self.assertTrue(
            PaymentLedger.objects.filter(
                user=self.child, entry_type="milestone_bonus",
                amount=Decimal("5.00"),
            ).exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_milestone_calls_game_loop(self, mock_gl):
        ms = ProjectMilestone.objects.create(
            project=self.project, title="Ch1",
        )
        ms.is_completed = True
        ms.save()
        mock_gl.assert_called_once()
        call_args = mock_gl.call_args
        self.assertEqual(call_args[0][0], self.child)
        self.assertEqual(call_args[0][1], "milestone_complete")
