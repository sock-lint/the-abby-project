"""REST creation recovers accepted UUIDs before validating new eligibility."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.movement.models import MovementType
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentGoalRecoveryAPITests(TestCase):
    def setUp(self):
        family = make_family("REST goal recovery", parents=[{"username": "rest-recovery-parent"}],
                             children=[{"username": "rest-recovery-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.at = datetime(2026, 10, 26, 12, tzinfo=datetime_timezone.utc)

    def data(self, **changes):
        return {"user_id": self.child.pk, "name": "Saved custom goal", "metric": "count", "target": "1",
                "unit": "actions", "trigger_type": "habit_log", "period": "custom",
                "start_date": "2026-10-26", "end_date": "2026-10-26", "request_id": str(uuid4()), **changes}

    def test_identical_uuid_recovers_after_custom_end_date_without_new_goal(self):
        data = self.data()
        with patch("django.utils.timezone.now", return_value=self.at):
            first = self.client.post("/api/challenges/goals/", data, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(days=1)):
            replay = self.client.post("/api/challenges/goals/", data, format="json")
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_new_requests_keep_field_errors_and_replays_keep_structural_validation(self):
        data = self.data()
        with patch("django.utils.timezone.now", return_value=self.at):
            self.assertEqual(self.client.post("/api/challenges/goals/", data, format="json").status_code, 201)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(days=1)):
            for changes, field in (({"request_id": str(uuid4())}, "end_date"),
                                   ({"target": "0.5"}, "target"),
                                   ({"end_date": "2026-10-25"}, "end_date"),
                                   ({"validate_current": False}, "validate_current")):
                with self.subTest(changes=changes):
                    result = self.client.post("/api/challenges/goals/", {**data, **changes}, format="json")
                    self.assertEqual(result.status_code, 400, result.data)
                    self.assertIn(field, result.data)
            changed = self.client.post("/api/challenges/goals/", {**data, "name": "Different"}, format="json")
        self.assertEqual(changed.status_code, 409, changed.data)
        self.assertIn("different goal details", changed.data["error"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)

    def test_saved_references_recover_but_new_requests_require_current_choices(self):
        skill = Skill.objects.create(name="REST saved skill", category=SkillCategory.objects.create(name="REST skills"))
        movement = MovementType.objects.create(name="REST recovery walk", slug="rest-recovery-walk")
        data = self.data(trigger_type="movement_session", movement_type_id=movement.pk,
                         skill_tags=[{"skill_id": skill.pk}], xp_reward=15)
        with patch("django.utils.timezone.now", return_value=self.at):
            first = self.client.post("/api/challenges/goals/", data, format="json")
            self.assertEqual(first.status_code, 201, first.data)
            MovementType.objects.filter(pk=movement.pk).update(is_active=False)
            skill.delete()
            replay = self.client.post("/api/challenges/goals/", data, format="json")
            self.assertEqual(replay.status_code, 201, replay.data)
            self.assertEqual(replay.data["id"], first.data["id"])
            new = self.client.post("/api/challenges/goals/", {**data, "request_id": str(uuid4())}, format="json")
            self.assertEqual(new.status_code, 400, new.data)
            self.assertIn("movement_type_id", new.data)
            MovementType.objects.filter(pk=movement.pk).update(is_active=True)
            new = self.client.post("/api/challenges/goals/", {**data, "request_id": str(uuid4())}, format="json")
            self.assertEqual(new.status_code, 400, new.data)
            self.assertIn("skill_tags", new.data)
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_missing_saved_occurrence_is_not_recreated(self):
        data = self.data()
        with patch("django.utils.timezone.now", return_value=self.at):
            first = self.client.post("/api/challenges/goals/", data, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        ChallengeOccurrence.objects.all().delete()
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(days=1)):
            replay = self.client.post("/api/challenges/goals/", data, format="json")
        self.assertEqual(replay.status_code, 404, replay.data)
        self.assertNotIn(first.data["id"], str(replay.data))
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
