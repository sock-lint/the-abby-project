"""Native parent goals reject stale authority before UUID recovery or awards."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.quests.goals import create_goal
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengePin
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeParentGoalAuthorityTests(TestCase):
    def setUp(self):
        family = make_family("Native goal authority", parents=[{"username": "native-goal-parent"}],
                             children=[{"username": "native-goal-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.other = make_family("Other native goal family").family
        self.data = {
            "user_id": self.child.pk, "name": "A native goal", "metric": "count", "target": Decimal("1"),
            "unit": "actions", "trigger_type": "habit_log", "period": "this_week", "coin_reward": 7,
        }

    def test_fresh_rows_reject_role_activity_and_membership_changes_before_creation(self):
        users = get_user_model().objects
        for member, change in (
            (self.parent, {"role": "child"}), (self.parent, {"is_active": False}),
            (self.parent, {"family_id": self.other.pk}), (self.child, {"role": "parent"}),
            (self.child, {"is_active": False}), (self.child, {"family_id": self.other.pk}),
        ):
            before = {field: getattr(member, field) for field in change}
            users.filter(pk=member.pk).update(**change)
            try:
                with self.subTest(member=member.username, change=change), self.assertRaises(ValueError):
                    create_goal(self.parent, self.child, self.data)
            finally:
                users.filter(pk=member.pk).update(**before)
        for model in (ChallengeGoal, ChallengeOccurrence, ChallengePin, CoinLedger):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_rest_request_revoked_after_permission_check_cannot_create(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        native = create_goal

        def revoke_then_create(parent, child, data, **kwargs):
            get_user_model().objects.filter(pk=parent.pk).update(role="child")
            return native(parent, child, data, **kwargs)

        with patch("apps.quests.goal_views.create_goal", side_effect=revoke_then_create):
            response = client.post("/api/challenges/goals/", self.data, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
