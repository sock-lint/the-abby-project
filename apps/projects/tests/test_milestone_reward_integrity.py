"""A saved milestone completion owns one atomic reward across reopenings."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.models import MilestoneSkillTag, Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import CompleteMilestoneIn
from apps.mcp_server.tools.projects import complete_milestone
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectMilestone
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class MilestoneRewardIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            "Milestone rewards", parents=[{"username": "milestone-parent"}],
            children=[{"username": "milestone-child"}, {"username": "milestone-sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        category = SkillCategory.objects.create(name="Milestone practice")
        self.skill = Skill.objects.create(name="Building phases", category=category)
        self.project = Project.objects.create(
            title="Birdhouse phases", created_by=self.parent, assigned_to=self.child,
            status="in_progress",
        )
        self.milestone = ProjectMilestone.objects.create(
            project=self.project, title="Build walls", bonus_amount=Decimal("5.00"),
        )
        MilestoneSkillTag.objects.create(milestone=self.milestone, skill=self.skill, xp_amount=23)
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.loop_patch = patch("apps.rpg.services.GameLoopService.on_task_completed")
        self.game_loop = self.loop_patch.start()
        self.addCleanup(self.loop_patch.stop)

    @property
    def url(self):
        return f"/api/projects/{self.project.pk}/milestones/{self.milestone.pk}/"

    def complete(self):
        response = self.client.post(self.url + "complete/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def complete_with_mcp(self):
        with override_user(self.parent):
            return complete_milestone(CompleteMilestoneIn(milestone_id=self.milestone.pk))

    def assert_one_reward(self):
        self.assertEqual(
            list(PaymentLedger.objects.filter(project=self.project).values_list("amount", "user_id", "entry_type")),
            [(Decimal("5.00"), self.child.pk, "milestone_bonus")],
        )
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 23)
        self.assertFalse(SkillProgress.objects.filter(user=self.sibling).exists())
        self.assertEqual(self.game_loop.call_count, 1)
        self.assertEqual(Notification.objects.filter(notification_type="milestone_completed").count(), 1)
        self.assertEqual(ActivityEvent.objects.filter(event_type="milestone.complete").count(), 1)

    def test_reopened_rest_completion_and_retries_reward_once(self):
        self.complete()
        self.milestone.refresh_from_db()
        completed_at = self.milestone.completed_at
        self.complete()
        response = self.client.patch(self.url, {"is_completed": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.complete()
        self.assert_one_reward()
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.completed_at, completed_at)

    def test_reassigned_project_and_changed_bonus_cannot_repay_milestone(self):
        self.complete()
        self.project.assigned_to = self.sibling
        self.project.save(update_fields=["assigned_to"])
        self.milestone.is_completed = False
        self.milestone.bonus_amount = Decimal("999.00")
        self.milestone.save()
        self.complete()
        self.assert_one_reward()

    def test_generic_completion_and_stale_model_instance_share_reward(self):
        stale = ProjectMilestone.objects.get(pk=self.milestone.pk)
        response = self.client.patch(self.url, {"is_completed": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        stale.is_completed = False
        stale.save()
        stale.is_completed = True
        stale.save()
        self.assert_one_reward()

    def test_failure_after_xp_rolls_back_completion_and_all_effects_then_retries(self):
        self.milestone.is_completed = True
        with patch("apps.payments.services.PaymentService.record_entry", side_effect=RuntimeError("synthetic milestone payout failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic milestone payout failure"):
                self.milestone.save()
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.is_completed)
        self.assertIsNone(self.milestone.completed_at)
        self.assertFalse(SkillProgress.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(Notification.objects.filter(notification_type="milestone_completed").exists())
        self.assertFalse(ActivityEvent.objects.filter(event_type="milestone.complete").exists())
        self.game_loop.assert_not_called()
        self.complete()
        self.assert_one_reward()

    def test_mcp_first_completion_awards_tagged_xp_once_and_keeps_coin_bonus(self):
        result = self.complete_with_mcp()
        self.assertEqual((result["xp_awarded"], result["coins_awarded"]), (23, 10))
        self.assert_one_reward()
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [10])

    def test_mcp_reopened_completion_cannot_replay_xp_or_coin_bonus(self):
        self.complete_with_mcp()
        self.milestone.is_completed = False
        self.milestone.save()
        result = self.complete_with_mcp()
        self.assertEqual((result["xp_awarded"], result["coins_awarded"]), (0, 0))
        self.assert_one_reward()
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [10])

    def test_rest_first_completion_cannot_claim_mcp_bonus_after_reopening(self):
        self.complete()
        self.milestone.is_completed = False
        self.milestone.save()
        result = self.complete_with_mcp()
        self.assertEqual((result["xp_awarded"], result["coins_awarded"]), (0, 0))
        self.assert_one_reward()
        self.assertFalse(CoinLedger.objects.exists())

    def test_mcp_coin_failure_rolls_back_shared_receipt_and_completion(self):
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("synthetic milestone coin failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic milestone coin failure"):
                self.complete_with_mcp()
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.is_completed)
        self.assertIsNone(self.milestone.completed_at)
        self.assertFalse(SkillProgress.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.game_loop.reset_mock()
        result = self.complete_with_mcp()
        self.assertEqual((result["xp_awarded"], result["coins_awarded"]), (23, 10))
        self.assert_one_reward()

    def test_mcp_foreign_family_and_sibling_cannot_complete_or_claim_rewards(self):
        foreign = make_family(
            "Foreign milestone household", parents=[{"username": "foreign-milestone-parent"}],
            children=[{"username": "foreign-milestone-child"}],
        )
        for actor in [foreign.parents[0], foreign.children[0], self.sibling]:
            with self.subTest(actor=actor.username), override_user(actor):
                with self.assertRaises(MCPNotFoundError):
                    complete_milestone(CompleteMilestoneIn(milestone_id=self.milestone.pk))
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.is_completed)
        self.assertFalse(SkillProgress.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.game_loop.assert_not_called()

    def test_mcp_assigned_child_keeps_existing_completion_permission(self):
        with override_user(self.child):
            result = complete_milestone(CompleteMilestoneIn(milestone_id=self.milestone.pk))
        self.assertEqual((result["xp_awarded"], result["coins_awarded"]), (23, 10))
        self.assert_one_reward()
