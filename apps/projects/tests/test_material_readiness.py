"""A supply can be ready without making a purchase or changing money records."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.achievements.models import SkillProgress
from apps.payments.models import PaymentLedger
from apps.projects.models import MaterialItem, Project, ProjectCollaborator
from apps.projects.planning import project_plan_snapshot
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family


class MaterialReadinessTests(APITestCase):
    def setUp(self):
        self.house = make_family(
            "Material family", parents=[{"username": "material-parent"}],
            children=[{"username": "material-child"}, {"username": "material-sibling"}],
        )
        self.other = make_family(
            "Other material family", parents=[{"username": "other-material-parent"}],
            children=[{"username": "other-material-child"}],
        )
        self.parent = self.house.parents[0]
        self.child = self.house.children[0]
        self.project = Project.objects.create(
            title="Get ready for math", created_by=self.parent, assigned_to=self.child,
            materials_budget="15.00",
        )
        self.material = MaterialItem.objects.create(
            project=self.project, name="Class notes", estimated_cost="3.00",
        )
        self.url = f"/api/projects/{self.project.pk}/materials/{self.material.pk}/mark-ready/"
        self.client.force_authenticate(self.child)

    def money_state(self):
        return MaterialItem.objects.filter(pk=self.material.pk).values(
            "estimated_cost", "actual_cost", "is_purchased", "purchased_at", "receipt_photo", "reimbursed",
        ).get()

    def reward_state(self):
        return (
            list(PaymentLedger.objects.order_by("pk").values()),
            list(CoinLedger.objects.order_by("pk").values()),
            list(SkillProgress.objects.order_by("pk").values()),
            list(CharacterProfile.objects.order_by("pk").values()),
        )

    def test_mark_ready_persists_and_is_returned_in_project_details(self):
        self.assertFalse(self.material.is_ready)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_ready"])
        self.assertFalse(response.data["is_purchased"])
        self.material.refresh_from_db()
        self.assertTrue(self.material.is_on_hand)
        self.assertTrue(self.material.is_ready)
        detail = self.client.get(f"/api/projects/{self.project.pk}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertTrue(detail.data["materials"][0]["is_ready"])

    def test_mark_ready_ignores_purchase_payload_and_never_writes_money_or_rewards(self):
        before_money = self.money_state()
        before_rewards = self.reward_state()
        before_project = Project.objects.filter(pk=self.project.pk).values().get()
        with CaptureQueriesContext(connection) as captured:
            response = self.client.post(self.url, {
                "actual_cost": "12.34", "estimated_cost": "99.00", "is_purchased": True,
                "purchased_at": "2026-01-01T00:00:00Z", "reimbursed": True,
            }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.money_state(), before_money)
        self.assertEqual(self.reward_state(), before_rewards)
        self.assertEqual(Project.objects.filter(pk=self.project.pk).values().get(), before_project)
        updates = [query["sql"] for query in captured if query["sql"].lstrip().upper().startswith("UPDATE")]
        self.assertEqual(len(updates), 1)
        self.assertIn('"is_on_hand"', updates[0])
        for column in ("actual_cost", "estimated_cost", "is_purchased", "purchased_at", "reimbursed"):
            self.assertNotIn(f'"{column}"', updates[0])

    def test_repeat_ready_is_idempotent_and_preserves_existing_purchase_details(self):
        purchased_at = timezone.now()
        MaterialItem.objects.filter(pk=self.material.pk).update(
            is_purchased=True, actual_cost="2.75", purchased_at=purchased_at,
            receipt_photo="receipts/synthetic.jpg", reimbursed=True,
        )
        before_money = self.money_state()
        before_rewards = self.reward_state()
        first = self.client.post(self.url, {}, format="json")
        second = self.client.post(self.url, {"actual_cost": "0.00", "reimbursed": False}, format="json")
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.data, second.data)
        self.assertEqual(self.money_state(), before_money)
        self.assertEqual(self.reward_state(), before_rewards)

    def test_legacy_purchased_material_is_ready_without_backfill(self):
        MaterialItem.objects.filter(pk=self.material.pk).update(is_purchased=True)
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_on_hand)
        self.assertTrue(self.material.is_ready)
        response = self.client.get(f"/api/projects/{self.project.pk}/materials/{self.material.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_ready"])

    def test_purchase_action_keeps_purchase_semantics_and_also_reports_ready(self):
        response = self.client.post(
            f"/api/projects/{self.project.pk}/materials/{self.material.pk}/mark-purchased/",
            {"actual_cost": "2.50"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_purchased"])
        self.assertTrue(response.data["is_ready"])
        self.material.refresh_from_db()
        self.assertEqual(self.material.actual_cost, Decimal("2.50"))
        self.assertIsNotNone(self.material.purchased_at)
        self.assertFalse(self.material.is_on_hand)

    def test_existing_purchase_patch_also_projects_ready(self):
        response = self.client.patch(
            f"/api/projects/{self.project.pk}/materials/{self.material.pk}/",
            {"is_purchased": True}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_ready"])

    def test_ready_projection_cannot_be_written_through_material_patch(self):
        response = self.client.patch(
            f"/api/projects/{self.project.pk}/materials/{self.material.pk}/",
            {"is_ready": True, "is_on_hand": True}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["is_ready"])
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_on_hand)

    def test_parent_and_project_collaborator_can_mark_material_ready(self):
        sibling = self.house.children[1]
        ProjectCollaborator.objects.create(project=self.project, user=sibling)
        for user in (self.parent, sibling):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                response = self.client.post(self.url, {}, format="json")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(response.data["is_ready"])

    def test_unassigned_family_draft_remains_accessible_to_its_parent(self):
        self.project.assigned_to = None
        self.project.save(update_fields=["assigned_to"])
        self.client.force_authenticate(self.parent)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_ready"])

    def test_sibling_foreign_family_and_unauthenticated_requests_cannot_mark_ready(self):
        for user, expected in (
            (self.house.children[1], 404), (self.other.parents[0], 404),
            (self.other.children[0], 404), (None, 401),
        ):
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.client.force_authenticate(user)
                response = self.client.post(self.url, {}, format="json")
                self.assertEqual(response.status_code, expected, response.content)
                self.assertNotIn(self.material.name, response.content.decode())
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_on_hand)
        self.assertFalse(self.material.is_purchased)

    def test_wrong_nested_project_cannot_mark_material_ready(self):
        second = Project.objects.create(
            title="Another accessible project", created_by=self.parent, assigned_to=self.child,
        )
        response = self.client.post(
            f"/api/projects/{second.pk}/materials/{self.material.pk}/mark-ready/", {}, format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_on_hand)

    def test_ready_change_invalidates_existing_plan_without_exposing_money_to_ai(self):
        version, original_context = project_plan_snapshot(self.project)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        current_version, current_context = project_plan_snapshot(self.project)
        self.assertNotEqual(current_version, version)
        self.assertEqual(current_context, original_context)
        self.client.force_authenticate(self.parent)
        response = self.client.post(f"/api/projects/{self.project.pk}/apply-plan/", {
            "plan_version": version,
            "plan": {
                "milestones": [{"title": "Prepare", "description": "Get ready."}],
                "steps": [{"title": "Study", "description": "Read notes.", "milestone_index": 0}],
                "materials": [],
            },
        }, format="json")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(self.project.steps.exists())
        self.assertFalse(self.project.milestones.exists())
