"""Material readiness and purchases through the real family-scoped API."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.mcp_server.shapes import material_to_dict
from apps.projects.models import MaterialItem, Project
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class MaterialApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared_fixtures.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Material Fixture Family", family_id=73,
            parents=[{"id": 701, "username": "material-fixture-parent"}],
            children=[{"id": 702, "username": "material-fixture-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.other_parent = make_family(
            "Other Material Fixture Family", family_id=74,
            parents=[{"id": 799, "username": "material-fixture-other-parent"}],
        ).parents[0]
        self.project = Project.objects.create(
            id=401, title="Get ready for a math test",
            created_by=self.parent, assigned_to=self.child,
        )
        self.material = MaterialItem.objects.create(
            id=701, project=self.project, name="Notebook or scratch paper",
            description="Use paper you already have or buy a notebook.",
            estimated_cost="3.00",
        )
        self.path = f"/api/projects/{self.project.pk}/materials/{self.material.pk}/"
        token = Token.objects.create(user=self.child, key="d" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_mcp_projection(self, body):
        self.material.refresh_from_db()
        self.assertEqual(material_to_dict(self.material), body)

    def test_unready_material_has_no_purchase_or_actual_cost(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json().get("is_ready"), False)
        body = self.assert_response_fixture(response, "material-unready.json")
        self.assertFalse(body["is_purchased"])
        self.assertIsNone(body["actual_cost"])
        self.assertIsNone(body["purchased_at"])
        self.assert_mcp_projection(body)
        listing = self.assert_response_fixture(
            self.client.get(f"/api/projects/{self.project.pk}/materials/"),
            "material-list.json",
        )
        self.assertEqual(listing["results"], [body])

    def test_ready_material_preserves_estimate_without_recording_a_purchase(self):
        body = self.assert_response_fixture(
            self.client.post(self.path + "mark-ready/", {}, format="json"),
            "material-ready.json",
        )
        self.assertTrue(body["is_ready"])
        self.assertFalse(body["is_purchased"])
        self.assertEqual(body["estimated_cost"], "3.00")
        self.assertIsNone(body["actual_cost"])
        self.assertIsNone(body["purchased_at"])
        self.assertFalse(body["reimbursed"])
        self.assertEqual(self.client.get(self.path).json(), body)
        self.assertEqual(self.client.post(self.path + "mark-ready/", {}, format="json").json(), body)
        self.assert_mcp_projection(body)
        self.assertTrue(self.material.is_on_hand)

    def test_explicit_zero_cost_purchase_is_ready_and_retains_zero(self):
        body = self.assert_response_fixture(
            self.client.post(self.path + "mark-purchased/", {"actual_cost": "0.00"}, format="json"),
            "material-purchased-zero.json",
        )
        self.assertTrue(body["is_purchased"])
        self.assertTrue(body["is_ready"])
        self.assertEqual(body["actual_cost"], "0.00")
        self.assertIsNotNone(body["purchased_at"])
        self.assert_mcp_projection(body)

    def test_readiness_can_be_cleared_and_replayed_without_recording_a_purchase(self):
        self.assertEqual(self.client.post(self.path + "mark-ready/", {}, format="json").status_code, 200)
        body = self.assert_response_fixture(
            self.client.post(self.path + "mark-not-ready/", {}, format="json"),
            "material-unready.json",
        )
        self.assertFalse(body["is_ready"])
        self.assertFalse(body["is_purchased"])
        self.assertIsNone(body["actual_cost"])
        self.assertIsNone(body["purchased_at"])
        self.assertEqual(self.client.get(self.path).json(), body)
        self.assertEqual(self.client.post(self.path + "mark-not-ready/", {}, format="json").json(), body)
        self.assert_mcp_projection(body)
        self.assertFalse(self.material.is_on_hand)

    def test_clearing_on_hand_does_not_erase_a_saved_purchase_or_its_readiness(self):
        self.assertEqual(self.client.post(self.path + "mark-ready/", {}, format="json").status_code, 200)
        purchase = self.client.post(
            self.path + "mark-purchased/", {"actual_cost": "2.75"}, format="json",
        )
        self.assertEqual(purchase.status_code, 200)
        body = self.assert_response_fixture(
            self.client.post(self.path + "mark-not-ready/", {}, format="json"),
            "material-purchased.json",
        )
        self.assertEqual(body, purchase.json())
        self.assertTrue(body["is_purchased"])
        self.assertTrue(body["is_ready"])
        self.assertEqual(body["actual_cost"], "2.75")
        self.assert_mcp_projection(body)
        self.assertFalse(self.material.is_on_hand)

    def test_purchase_reports_actual_cost_separately_from_estimate(self):
        body = self.assert_response_fixture(
            self.client.post(self.path + "mark-purchased/", {"actual_cost": "2.75"}, format="json"),
            "material-purchased.json",
        )
        self.assertTrue(body["is_ready"])
        self.assertTrue(body["is_purchased"])
        self.assertEqual(body["estimated_cost"], "3.00")
        self.assertEqual(body["actual_cost"], "2.75")
        self.assert_mcp_projection(body)

    def test_foreign_family_cannot_change_material_readiness(self):
        before = MaterialItem.objects.filter(pk=self.material.pk).values().get()
        self.client.force_authenticate(self.other_parent)
        for action in ("mark-ready/", "mark-not-ready/"):
            with self.subTest(action=action):
                self.assert_response_fixture(
                    self.client.post(self.path + action, {}, format="json"),
                    "material-not-owned.json", status=404,
                )
        self.assertEqual(MaterialItem.objects.filter(pk=self.material.pk).values().get(), before)
