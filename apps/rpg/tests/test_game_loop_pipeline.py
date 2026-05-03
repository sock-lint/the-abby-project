"""Audit H7: ``GameLoopService.on_task_completed`` runs each step inside
its own ``transaction.atomic`` savepoint with a try/except. A late-stage
failure (quest crash, chronicle hiccup) MUST NOT roll back early-stage
writes (the streak update, the check-in coin grant).

Pre-fix the whole function was wrapped in a single outer atomic. A drop
exception would unwind the streak; a quest exception couldn't (caught)
but the buffered writes from earlier steps were still in-flight until
the function returned.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile
from apps.rpg.services import GameLoopService


class GameLoopStepIsolationTests(TestCase):
    """Failure in step N must not roll back writes from steps 1..N-1.

    Each test crashes a specific step and asserts that the side-effects
    from the prior steps are still present in the DB after the loop
    returns. The harness uses ``patch`` to inject ``Exception("boom")``
    at each step's primary entry point.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        # Pre-seed the character profile so step 1 can update streak.
        # ``StreakService.record_activity`` get_or_creates anyway, but
        # being explicit makes the test setup readable.
        CharacterProfile.objects.get_or_create(user=self.user)

    def _streak_value(self):
        return CharacterProfile.objects.get(user=self.user).login_streak

    def _coin_balance(self):
        return CoinService.get_balance(self.user)

    def test_drop_step_failure_preserves_streak_update(self):
        # Step 4 (drops) crashes. Steps 1 (streak), 2 (check-in coin),
        # and 3 (milestone notify) ran inside their own savepoints
        # earlier in the pipeline — their writes must persist.
        before_streak = self._streak_value()
        with patch(
            "apps.rpg.services.DropService.process_drops",
            side_effect=RuntimeError("simulated drop failure"),
        ):
            result = GameLoopService.on_task_completed(
                self.user, "clock_out", {"drops_allowed": True},
            )
        # Streak still updated (step 1 committed).
        self.assertEqual(self._streak_value(), before_streak + 1)
        # The pipeline continued through the remaining steps and returned
        # the partial result.
        self.assertIsNotNone(result["streak"])
        # Drops field defaults to [] when the step failed.
        self.assertEqual(result["drops"], [])

    def test_quest_step_failure_preserves_check_in_bonus(self):
        # Step 5 (quest) crashes. Step 2's check-in coin grant must
        # persist — it's a real CoinLedger row that the parent reads.
        with patch(
            "apps.quests.services.QuestService.record_progress",
            side_effect=RuntimeError("simulated quest failure"),
        ):
            GameLoopService.on_task_completed(self.user, "clock_out", {})
        # Check-in bonus persisted as a CoinLedger ADJUSTMENT row.
        bonus_rows = CoinLedger.objects.filter(
            user=self.user,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description="Daily check-in bonus",
        )
        self.assertEqual(bonus_rows.count(), 1)

    def test_chronicle_step_failure_preserves_quest_progress(self):
        # Step 6 (chronicle) crashes. Step 5's quest result must still
        # appear in the returned dict.
        with patch(
            "apps.rpg.services.GameLoopService._record_chronicle_firsts",
            side_effect=RuntimeError("simulated chronicle failure"),
        ):
            result = GameLoopService.on_task_completed(
                self.user, "clock_out", {},
            )
        # The quest step ran and reported a result (None is a valid
        # return when there's no active quest matching the trigger —
        # the assertion is about the structure, not a positive value).
        self.assertIn("quest", result)
        self.assertIsNone(result["chronicle"])

    def test_streak_step_failure_does_not_block_subsequent_steps(self):
        # If step 1 itself fails, downstream steps see ``streak=None``
        # in the result dict and gracefully skip the streak-dependent
        # behaviour (no crash, no half-applied state).
        with patch(
            "apps.rpg.services.StreakService.record_activity",
            side_effect=RuntimeError("simulated streak failure"),
        ):
            result = GameLoopService.on_task_completed(
                self.user, "clock_out", {},
            )
        # Pipeline ran to completion despite the early failure.
        self.assertIsNone(result["streak"])
        # No check-in coin since step 2 short-circuits when
        # streak is None.
        self.assertFalse(
            CoinLedger.objects.filter(
                user=self.user, description="Daily check-in bonus",
            ).exists(),
        )

    def test_no_step_failure_returns_full_payload(self):
        # Smoke test of the happy path — pipeline returns all 7 keys.
        result = GameLoopService.on_task_completed(self.user, "clock_out", {})
        self.assertIn("trigger_type", result)
        self.assertIn("streak", result)
        self.assertIn("notifications", result)
        self.assertIn("drops", result)
        self.assertIn("quest", result)
        self.assertIn("daily_challenge", result)
        self.assertIn("chronicle", result)
        self.assertEqual(result["trigger_type"], "clock_out")
