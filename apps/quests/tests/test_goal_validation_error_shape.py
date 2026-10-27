"""Deferred goal eligibility preserves REST field-error lists."""
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.movement.models import MovementType
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GoalEligibilityErrorShapeAPITests(TestCase):
    def setUp(self):
        household = make_family(
            "Goal validation response", parents=[{"username": "goal-shape-parent"}],
            children=[{"username": "goal-shape-child"}],
        )
        household.family.timezone = "UTC"
        household.family.save(update_fields=["timezone"])
        self.parent, self.child = household.parents[0], household.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.at = datetime(2026, 10, 26, 12, tzinfo=datetime_timezone.utc)

    def assert_field_error(self, field, message, **changes):
        data = {
            "request_id": str(uuid4()), "user_id": self.child.pk, "name": "A new family goal",
            "trigger_type": "habit_log", "metric": "count", "target": "3", "unit": "actions",
            "period": "this_week", **changes,
        }
        with patch("django.utils.timezone.now", return_value=self.at):
            response = self.client.post("/api/challenges/goals/", data, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.json(), {field: [message]})
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_expired_custom_period_returns_end_date_error_list(self):
        self.assert_field_error(
            "end_date", "Use an end date on or after today/start, within one year.",
            period="custom", start_date="2026-10-25", end_date="2026-10-25",
        )

    def test_custom_period_beyond_current_year_returns_end_date_error_list(self):
        self.assert_field_error(
            "end_date", "Use an end date on or after today/start, within one year.",
            period="custom", start_date="2027-10-30", end_date="2027-10-30",
        )

    def test_inactive_movement_returns_activity_field_error_list(self):
        movement = MovementType.objects.create(name="Unavailable practice", slug="unavailable-goal-practice", is_active=False)
        self.assert_field_error(
            "movement_type_id", "Choose an available activity type.",
            trigger_type="movement_session", movement_type_id=movement.pk,
        )

    def test_missing_reward_skill_returns_skill_tags_error_list(self):
        self.assert_field_error(
            "skill_tags", "Choose existing skills.",
            xp_reward=15, skill_tags=[{"skill_id": 123456789}],
        )
