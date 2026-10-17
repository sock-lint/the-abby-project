"""Real lifecycle previews shared with the Settings client, without secrets."""
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LifecycleApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        self.household = make_family(
            "Lifecycle Fixture Family", family_id=601,
            parents=[
                {"id": 610, "username": "fixture-parent", "display_name": "Alex"},
                {"id": 611, "username": "fixture-coparent", "display_name": "Sam"},
            ],
            children=[{"id": 612, "username": "fixture-child", "display_name": "River"}],
        )
        from apps.habits.models import Habit
        from apps.projects.models import Project

        parent, child = self.household.parents[0], self.household.children[0]
        Project.objects.create(title="Synthetic shared project", created_by=parent, assigned_to=child)
        Habit.objects.create(name="Synthetic shared habit", created_by=parent, user=child)

    def preview(self, user, name):
        credential = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {credential.key}")
        response = self.client.get("/api/account/lifecycle/")
        body = self.assert_response_fixture(response, name)
        self.assertNotIn(credential.key, response.content.decode())
        self.assertNotIn("password", body)
        return body

    def test_parent_preview_matches_shared_contract(self):
        body = self.preview(self.household.parents[0], "lifecycle-preview.json")
        self.assertTrue(body["can_delete_account"])
        self.assertFalse(body["can_close_family"])
        self.assertEqual(body["successors"][0]["id"], self.household.parents[1].pk)
        self.assertEqual(body["shared_work"]["projects"], 1)
        self.assertEqual(body["shared_work"]["habits"], 1)

    def test_child_preview_matches_shared_contract(self):
        body = self.preview(self.household.children[0], "lifecycle-child-preview.json")
        self.assertTrue(body["can_delete_account"])
        self.assertFalse(body["can_close_family"])
        self.assertEqual(body["successors"], [])

    def test_last_parent_preview_includes_inactive_members_in_closure_impact(self):
        parent = self.household.parents[1]
        parent.is_active = False
        parent.save(update_fields=["is_active"])
        body = self.preview(self.household.parents[0], "lifecycle-close-preview.json")
        self.assertFalse(body["can_delete_account"])
        self.assertTrue(body["can_close_family"])
        self.assertEqual(body["family_members"], {"parents": 2, "children": 1})
