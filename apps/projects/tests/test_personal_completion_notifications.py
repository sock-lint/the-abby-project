"""Parent project completion receipts use their personal destination and copy."""
from decimal import Decimal
from unittest.mock import patch

from apps.achievements.models import MilestoneSkillTag, Skill, SkillCategory, SkillProgress
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import CompleteMilestoneIn
from apps.mcp_server.tools.projects import complete_milestone
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import (
    MilestoneCompletionRewardReceipt, Project, ProjectCompletionRewardReceipt, ProjectMilestone,
)
from apps.rewards.models import CoinLedger
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class PersonalProjectCompletionNotificationTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "completion-owner"}, {"username": "completion-coparent"}]
    family_children = [{"username": "completion-child"}]

    def setUp(self):
        self.parent, self.coparent = self.parents
        self.child = self.children[0]
        self.client.force_authenticate(self.parent)

    def receipt(self, user):
        return Notification.objects.get(user=user, notification_type="project_approved")

    def test_personal_create_activate_and_complete_notifies_completion_once_in_my_space(self):
        created = self.client.post("/api/projects/", {"title": "Shelf"},
                                   format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(created.status_code, 201, created.content)
        project_id = created.data["id"]
        activated = self.client.post(f"/api/projects/{project_id}/activate/", {},
                                     format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(activated.status_code, 200, activated.content)
        for _ in range(2):
            completed = self.client.post(f"/api/projects/{project_id}/approve/", {},
                                         format="json", HTTP_X_ABBY_SPACE="personal")
            self.assertEqual(completed.status_code, 200, completed.content)
        receipt = self.receipt(self.parent)
        self.assertEqual((receipt.title, receipt.message, receipt.link), (
            "Project completed: Shelf", "You completed your project! Great work!",
            f"/projects/{project_id}?space=personal",
        ))
        self.assertEqual(ProjectCompletionRewardReceipt.objects.get(project_id=project_id).user_id, self.parent.pk)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, reason="project_bonus").count(), 1)
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(Notification.objects.filter(user__in=[self.child, self.coparent]).exists())
        self.assertEqual(self.client.get(f"/api/notifications/{receipt.pk}/").json()["link"], receipt.link)
        outsider = make_family("Other completion family", parents=[{"username": "completion-outsider"}]).parents[0]
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(f"/api/notifications/{receipt.pk}/").status_code, 404)

    def test_child_family_approval_keeps_existing_copy_link_and_cash_reward_once(self):
        project = Project.objects.create(
            title="Child shelf", created_by=self.parent, assigned_to=self.child,
            status="in_review", bonus_amount="12.00",
        )
        for _ in range(2):
            approved = self.client.post(f"/api/projects/{project.pk}/approve/", {}, format="json")
            self.assertEqual(approved.status_code, 200, approved.content)
        receipt = self.receipt(self.child)
        self.assertEqual((receipt.title, receipt.message, receipt.link), (
            "Project approved: Child shelf", "Your project has been approved! Great work!",
            f"/projects/{project.pk}",
        ))
        self.assertEqual(list(PaymentLedger.objects.filter(user=self.child).values_list("amount", flat=True)),
                         [Decimal("12.00")])
        self.assertFalse(Notification.objects.filter(user__in=[self.parent, self.coparent],
                                                    notification_type="project_approved").exists())

    def test_family_save_of_parent_owned_project_uses_completion_copy_without_changing_family_pay(self):
        project = Project.objects.create(
            title="Parent shelf", created_by=self.coparent, assigned_to=self.parent,
            status="in_review", bonus_amount="40.00",
        )
        approved = self.client.post(f"/api/projects/{project.pk}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        receipt = self.receipt(self.parent)
        self.assertEqual((receipt.title, receipt.message, receipt.link), (
            "Project completed: Parent shelf", "You completed your project! Great work!",
            f"/projects/{project.pk}?space=personal",
        ))
        self.assertEqual(list(PaymentLedger.objects.filter(user=self.parent).values_list("amount", flat=True)),
                         [Decimal("40.00")])

    def test_personal_milestone_receipt_opens_my_space_and_replays_once(self):
        created = self.client.post("/api/projects/", {"title": "Personal shelf"},
                                   format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(created.status_code, 201, created.content)
        project_id = created.data["id"]
        milestone = self.client.post(f"/api/projects/{project_id}/milestones/", {
            "title": "Cut boards", "bonus_amount": "5.00",
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(milestone.status_code, 201, milestone.content)
        category = SkillCategory.objects.create(name="Milestone notification practice")
        skill = Skill.objects.create(name="Making phases", category=category)
        MilestoneSkillTag.objects.create(milestone_id=milestone.data["id"], skill=skill, xp_amount=11)
        url = f"/api/projects/{project_id}/milestones/{milestone.data['id']}/complete/"
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push:
            for _ in range(2):
                completed = self.client.post(url, {}, format="json", HTTP_X_ABBY_SPACE="personal")
                self.assertEqual(completed.status_code, 200, completed.content)
        note = Notification.objects.get(user=self.parent, notification_type="milestone_completed")
        expected = f"/projects/{project_id}?space=personal"
        with self.subTest(surface="saved_destination"):
            self.assertEqual(note.link, expected)
        with self.subTest(surface="push_destination"):
            routes = [(call.args[0], call.args[3]) for call in push.call_args_list
                      if call.args[4] == "milestone_completed"]
            self.assertEqual(routes, [(self.parent.pk, expected)])
        self.assertEqual(MilestoneCompletionRewardReceipt.objects.get(milestone_id=milestone.data["id"]).user_id,
                         self.parent.pk)
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=skill).xp_points, 11)
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(Notification.objects.filter(user__in=[self.child, self.coparent],
                                                    notification_type="milestone_completed").exists())
        detail = self.client.get(f"/api/notifications/{note.pk}/")
        self.assertEqual(detail.json()["link"], expected)
        outsider = make_family("Other milestone family", parents=[{"username": "milestone-outsider"}]).parents[0]
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(f"/api/notifications/{note.pk}/").status_code, 404)

    def test_child_milestone_receipt_keeps_native_link_and_cash_reward_once(self):
        project = Project.objects.create(title="Child milestones", assigned_to=self.child, created_by=self.parent)
        milestone = ProjectMilestone.objects.create(project=project, title="Child phase", bonus_amount="5.00")
        for _ in range(2):
            completed = self.client.post(f"/api/projects/{project.pk}/milestones/{milestone.pk}/complete/",
                                         {}, format="json")
            self.assertEqual(completed.status_code, 200, completed.content)
        note = Notification.objects.get(user=self.child, notification_type="milestone_completed")
        self.assertEqual(note.link, f"/projects/{project.pk}")
        self.assertEqual(list(PaymentLedger.objects.filter(user=self.child).values_list("amount", flat=True)),
                         [Decimal("5.00")])
        self.assertFalse(Notification.objects.filter(user__in=[self.parent, self.coparent],
                                                    notification_type="milestone_completed").exists())
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get(f"/api/notifications/{note.pk}/").json()["link"], note.link)

    def test_mcp_milestone_destination_follows_owner_instead_of_acting_coparent(self):
        for owner in (self.parent, self.child):
            with self.subTest(owner=owner.pk):
                project = Project.objects.create(title=f"Owner {owner.pk} project", assigned_to=owner,
                                                 created_by=self.coparent)
                milestone = ProjectMilestone.objects.create(project=project, title=f"Owner {owner.pk} milestone")
                with override_user(self.coparent):
                    completed = complete_milestone(CompleteMilestoneIn(milestone_id=milestone.pk))
                    replay = complete_milestone(CompleteMilestoneIn(milestone_id=milestone.pk))
                self.assertTrue(completed["milestone"]["is_completed"])
                self.assertTrue(replay["already_completed"])
                note = Notification.objects.get(user=owner, notification_type="milestone_completed")
                self.assertEqual(note.link, f"/projects/{project.pk}" +
                                 ("?space=personal" if owner.role == "parent" else ""))
        self.assertFalse(PaymentLedger.objects.exists())
