"""Saved co-op history preserves contributions without a departed member's profile."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


FIXED_NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="UTC", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ParticipantPrivacyResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    @patch("django.utils.timezone.now", return_value=FIXED_NOW)
    def test_saved_history_masks_departed_current_name_but_retains_current_family_and_contributions(self, _now):
        household = make_family("Synthetic shared practice", family_id=86,
            parents=[{"id": 121, "username": "fixture-coop-parent"}], children=[
                {"id": 122, "username": "fixture-coop-staying", "display_name": "Original shared name"},
                {"id": 123, "username": "fixture-coop-departing", "display_name": "Originally shared participant"},
            ])
        other = make_family("Synthetic later household", family_id=87,
            parents=[{"id": 124, "username": "fixture-coop-other-parent"}])
        staying, departing = household.children
        definition = QuestDefinition.objects.create(id=1201, name="Saved cooperative practice",
            description="A synthetic saved team challenge.", is_system=True, is_cooperative=True,
            quest_type="collection", target_value=10, duration_days=7)
        quest = Quest.objects.create(id=1202, definition=definition, status="completed",
            start_date=FIXED_NOW - timedelta(days=7), end_date=FIXED_NOW,
            current_progress=10, reward_items_snapshot=[])
        QuestParticipant.objects.create(id=1203, quest=quest, user=staying, contribution=7)
        QuestParticipant.objects.create(id=1204, quest=quest, user=departing, contribution=3)
        Token.objects.create(user=staying, key="q" * 40)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + "q" * 40)
        before = self.client.get("/api/quests/history/")
        self.assertEqual(before.status_code, 200)
        self.assertEqual([row["user_name"] for row in before.json()[0]["participants"]],
                         ["Original shared name", "Originally shared participant"])
        # Membership changes are synthetic fixture setup; current labels are
        # deliberately different from names visible during the saved campaign.
        type(staying).objects.filter(pk=staying.pk).update(display_name="Current shared name")
        type(departing).objects.filter(pk=departing.pk).update(
            family=other.family, display_name="Private later household name")
        response = self.client.get("/api/quests/history/")
        self.assertEqual(response.status_code, 200)
        participants = response.json()[0]["participants"]
        self.assertEqual(participants, [
            {"id": 1203, "user": 122, "user_name": "Current shared name", "contribution": 7},
            {"id": 1204, "user": 123, "user_name": "Former participant", "contribution": 3},
        ])
        self.assertNotIn("Private later household name", response.content.decode())
        self.assert_response_fixture(response, "quest-history-former-participant.json")
