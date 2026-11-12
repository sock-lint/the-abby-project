"""Unavailable goal members must not look like a saved-request conflict."""
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.quests.goals import create_goal
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GoalAuthorityResponseTests(TestCase):
    def setUp(self):
        family = make_family("Goal response family", parents=[{"username": "response-parent"}],
                             children=[{"username": "response-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.other = make_family("Other goal response family").family
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.data = {
            "request_id": str(uuid4()), "user_id": self.child.pk, "name": "Saved work",
            "metric": "count", "target": "2", "unit": "actions", "trigger_type": "habit_log",
            "period": "this_week", "coin_reward": 7,
        }

    def post(self, **changes):
        return self.client.post("/api/challenges/goals/", {**self.data, **changes}, format="json")

    def assert_no_saved_work(self):
        for model in (ChallengeGoal, ChallengeOccurrence, CoinLedger):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_inactive_child_is_not_a_saved_request_conflict(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        response = self.post()
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.json(), {"error": "Child not found"})
        self.assert_no_saved_work()

    def test_child_changes_after_initial_lookup_return_not_found(self):
        users = get_user_model().objects
        for change in ({"is_active": False}, {"role": "parent"}, {"family_id": self.other.pk}):
            before = {field: getattr(self.child, field) for field in change}

            def change_then_create(parent, child, data, **kwargs):
                users.filter(pk=child.pk).update(**change)
                return create_goal(parent, child, data, **kwargs)

            try:
                with self.subTest(change=change), patch(
                    "apps.quests.goal_views.create_goal", side_effect=change_then_create,
                ):
                    response = self.post()
                    self.assertEqual(response.status_code, 404, response.data)
                    self.assertEqual(response.json(), {"error": "Child not found"})
                    self.assert_no_saved_work()
            finally:
                users.filter(pk=self.child.pk).update(**before)

    def test_actor_changes_after_permission_check_return_forbidden(self):
        users = get_user_model().objects
        for change in ({"is_active": False}, {"role": "child"}, {"family_id": self.other.pk}):
            before = {field: getattr(self.parent, field) for field in change}

            def change_then_create(parent, child, data, **kwargs):
                users.filter(pk=parent.pk).update(**change)
                return create_goal(parent, child, data, **kwargs)

            try:
                with self.subTest(change=change), patch(
                    "apps.quests.goal_views.create_goal", side_effect=change_then_create,
                ):
                    response = self.post()
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertIn("error", response.json())
                    self.assert_no_saved_work()
            finally:
                users.filter(pk=self.parent.pk).update(**before)

    def test_saved_uuid_replay_for_inactive_child_is_not_a_conflict(self):
        saved = self.post()
        self.assertEqual(saved.status_code, 201, saved.data)
        goal = ChallengeGoal.objects.get()
        before = (goal.request_id, goal.request_fingerprint, goal.updated_at)
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        response = self.post()
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.json(), {"error": "Child not found"})
        goal.refresh_from_db()
        self.assertEqual((goal.request_id, goal.request_fingerprint, goal.updated_at), before)
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_changed_saved_details_still_return_a_request_conflict(self):
        self.assertEqual(self.post().status_code, 201)
        response = self.post(name="Different saved work")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertIn("request_id", response.json()["error"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())
