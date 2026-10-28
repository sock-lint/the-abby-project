"""Parent project completion receipts use their personal destination and copy."""
from decimal import Decimal

from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectCompletionRewardReceipt
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
