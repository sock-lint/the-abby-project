"""Parent-owned project terms and once-only completion rewards across clients."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import ProjectSkillTag, Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import UpdateProjectStatusIn
from apps.mcp_server.tools.projects import update_project_status
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProjectCompletionRewardIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            "Project reward integrity",
            parents=[{"username": "reward-parent"}],
            children=[{"username": "reward-child"}, {"username": "reward-sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        category = SkillCategory.objects.create(name="Project practice")
        self.skill = Skill.objects.create(name="Building", category=category)
        self.project = Project.objects.create(
            title="Birdhouse", created_by=self.parent, assigned_to=self.child,
            status="in_review", difficulty=2, bonus_amount=Decimal("12.00"),
        )
        ProjectSkillTag.objects.create(project=self.project, skill=self.skill, xp_weight=1)
        self.client = APIClient()
        self.loop_patch = patch("apps.rpg.services.GameLoopService.on_task_completed")
        self.game_loop = self.loop_patch.start()
        self.addCleanup(self.loop_patch.stop)

    def approve(self):
        self.client.force_authenticate(self.parent)
        response = self.client.post(f"/api/projects/{self.project.pk}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def assert_one_completion_award(self):
        self.assertEqual(
            list(PaymentLedger.objects.filter(project=self.project).values_list("amount", "entry_type")),
            [(Decimal("12.00"), "project_bonus")],
        )
        self.assertEqual(
            list(CoinLedger.objects.filter(reason__in=["project_bonus", "bounty_bonus"]).values_list("amount", flat=True)),
            [20],
        )
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 100)
        self.assertEqual(self.game_loop.call_count, 1)
        self.assertEqual(Notification.objects.filter(notification_type="project_approved").count(), 1)
        self.assertEqual(ActivityEvent.objects.filter(event_type="project.complete").count(), 1)

    def malicious_update(self, method):
        self.client.force_authenticate(self.child)
        response = getattr(self.client, method)(
            f"/api/projects/{self.project.pk}/",
            {"title": "Self-awarded", "status": "completed", "bonus_amount": "999.00",
             "difficulty": 5, "payment_kind": "bounty", "hourly_rate_override": "99.00",
             "assigned_to_id": self.sibling.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.project.refresh_from_db()
        self.assertEqual(
            (self.project.title, self.project.status, self.project.bonus_amount,
             self.project.difficulty, self.project.payment_kind, self.project.hourly_rate_override,
             self.project.assigned_to_id),
            ("Birdhouse", "in_review", Decimal("12.00"), 2, "required", None, self.child.pk),
        )
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())
        self.game_loop.assert_not_called()

    def test_child_cannot_patch_reward_terms_or_status(self):
        self.malicious_update("patch")

    def test_child_cannot_put_reward_terms_or_status(self):
        self.malicious_update("put")

    def test_child_submit_and_parent_edit_approve_still_work(self):
        self.client.force_authenticate(self.parent)
        response = self.client.patch(
            f"/api/projects/{self.project.pk}/", {"title": "Updated birdhouse"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_authenticate(self.child)
        response = self.client.post(f"/api/projects/{self.project.pk}/submit/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], "in_review")
        self.approve()
        self.assert_one_completion_award()

    def test_approval_retry_and_reopened_review_do_not_repeat_awards(self):
        self.approve()
        self.approve()
        response = self.client.post(
            f"/api/projects/{self.project.pk}/request-changes/", {"notes": "Touch up"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_authenticate(self.child)
        response = self.client.post(f"/api/projects/{self.project.pk}/submit/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.approve()
        self.assert_one_completion_award()

    def test_parent_reassignment_and_changed_reward_terms_cannot_repay_project(self):
        self.approve()
        response = self.client.patch(
            f"/api/projects/{self.project.pk}/",
            {"status": "in_progress", "assigned_to_id": self.sibling.pk,
             "bonus_amount": "999.00", "difficulty": 5, "payment_kind": "bounty"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.approve()
        self.assert_one_completion_award()
        self.assertFalse(PaymentLedger.objects.filter(user=self.sibling).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.sibling).exists())

    def test_parent_generic_completion_updates_also_pay_once(self):
        self.client.force_authenticate(self.parent)
        for status in ("completed", "in_progress", "completed"):
            response = self.client.patch(
                f"/api/projects/{self.project.pk}/", {"status": status}, format="json",
            )
            self.assertEqual(response.status_code, 200, response.content)
        self.assert_one_completion_award()

    def test_mcp_completion_and_rest_retry_share_one_award(self):
        with override_user(self.parent):
            result = update_project_status(UpdateProjectStatusIn(project_id=self.project.pk, status="completed"))
        self.assertEqual(result["status"], "completed")
        self.approve()
        self.assert_one_completion_award()

    def test_stale_model_instances_cannot_repeat_completion_awards(self):
        first = Project.objects.get(pk=self.project.pk)
        stale = Project.objects.get(pk=self.project.pk)
        first.status = "completed"
        first.save()
        stale.status = "in_progress"
        stale.save()
        stale.status = "completed"
        stale.save()
        self.assert_one_completion_award()

    def test_failed_award_rolls_back_status_effects_and_can_retry(self):
        self.project.status = "completed"
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("synthetic payout failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic payout failure"):
                self.project.save()
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "in_review")
        self.assertIsNone(self.project.completed_at)
        self.assertFalse(Notification.objects.filter(notification_type="project_approved").exists())
        self.assertFalse(ActivityEvent.objects.filter(event_type="project.complete").exists())
        self.approve()
        self.assert_one_completion_award()

    def test_failure_between_coin_and_money_writes_leaves_no_partial_reward(self):
        self.project.status = "completed"
        with patch("apps.payments.services.PaymentService.record_entry", side_effect=RuntimeError("synthetic ledger failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic ledger failure"):
                self.project.save()
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "in_review")
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())
        self.approve()
        self.assert_one_completion_award()
