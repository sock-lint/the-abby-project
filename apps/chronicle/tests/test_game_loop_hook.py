"""Tests for GameLoopService._record_chronicle_firsts pipeline step.

Core contract: record_first is called with the right slug; duplicates
don't double-write; chronicle failures don't break the parent flow.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry
from apps.rpg.constants import TriggerType
from apps.rpg.services import GameLoopService

User = get_user_model()


class ChronicleHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    @patch("apps.rpg.services.random.random", return_value=1.0)  # suppress drops
    def test_project_complete_bounty_emits_first_bounty_payout(self, _):
        GameLoopService.on_task_completed(
            self.user,
            TriggerType.PROJECT_COMPLETE,
            {"payment_kind": "bounty"},
        )
        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user, kind="first_ever", event_slug="first_bounty_payout"
            ).exists()
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_duplicate_does_not_create_second_entry(self, _):
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="first_bounty_payout").count(), 1
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_non_bounty_project_emits_first_project_completed(self, _):
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "required"})
        self.assertTrue(
            ChronicleEntry.objects.filter(event_slug="first_project_completed").exists()
        )
        self.assertFalse(
            ChronicleEntry.objects.filter(event_slug="first_bounty_payout").exists()
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    @patch("apps.chronicle.services.ChronicleService.record_first", side_effect=Exception("db exploded"))
    def test_chronicle_exception_does_not_break_parent_flow(self, _mock_record, _mock_random):
        result = GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        # Outer flow still returns, does not raise.
        self.assertIsNotNone(result)
        # And the chronicle sub-result is empty, not crashing.
        self.assertIn("chronicle", result)
