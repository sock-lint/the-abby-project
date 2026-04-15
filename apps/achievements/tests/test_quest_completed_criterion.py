"""Tests for the QUEST_COMPLETED badge criterion + award_coins gating.

Covers the new pieces added for pack-authored "cosmetic-title" badges:

- The ``quest_completed`` evaluator in ``apps.achievements.criteria`` —
  matches on quest definition name (with list support for any-of).
- The ``Badge.award_coins`` field — when False, ``BadgeService`` must
  NOT award rarity-scaled coins on earn, even though the badge still
  gets the ``UserBadge`` row and any ``xp_bonus``.
- The integration: completing a quest runs badge evaluation (via
  AwardService when xp > 0, directly when xp == 0) so the quest-
  completion badge attaches on the same transaction.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.achievements.criteria import _quest_completed
from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService


class QuestCompletedEvaluatorTests(TestCase):
    """Unit tests for the _quest_completed criterion checker."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="qc-evaluator", password="pw", role="child",
        )
        self.definition = QuestDefinition.objects.create(
            name="Seven Nights of Stories",
            description="read stories",
            quest_type="collection",
            target_value=5,
            duration_days=7,
        )

    def _complete_quest(self) -> Quest:
        quest = Quest.objects.create(
            definition=self.definition,
            status=Quest.Status.COMPLETED,
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=6),
            current_progress=5,
        )
        QuestParticipant.objects.create(quest=quest, user=self.user)
        return quest

    def test_returns_true_when_quest_completed_by_name(self) -> None:
        self._complete_quest()
        self.assertTrue(
            _quest_completed(self.user, {"quest_name": "Seven Nights of Stories"})
        )

    def test_returns_false_when_quest_not_completed(self) -> None:
        # Active but not completed
        quest = Quest.objects.create(
            definition=self.definition,
            status=Quest.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.user)
        self.assertFalse(
            _quest_completed(self.user, {"quest_name": "Seven Nights of Stories"})
        )

    def test_returns_false_when_user_not_participant(self) -> None:
        other = User.objects.create_user(
            username="qc-other", password="pw", role="child",
        )
        quest = Quest.objects.create(
            definition=self.definition,
            status=Quest.Status.COMPLETED,
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=6),
        )
        QuestParticipant.objects.create(quest=quest, user=other)
        # user is not a participant — should not qualify
        self.assertFalse(
            _quest_completed(self.user, {"quest_name": "Seven Nights of Stories"})
        )

    def test_accepts_list_of_names_any_of(self) -> None:
        self._complete_quest()
        self.assertTrue(
            _quest_completed(
                self.user,
                {"quest_names": ["Nonexistent", "Seven Nights of Stories"]},
            )
        )

    def test_missing_criteria_value_returns_false(self) -> None:
        self._complete_quest()
        self.assertFalse(_quest_completed(self.user, {}))


class BadgeAwardCoinsGatingTests(TestCase):
    """Ensure Badge.award_coins=False suppresses the coin payout."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="coin-gate", password="pw", role="child",
        )
        self.badge_paying = Badge.objects.create(
            name="Paying Badge",
            description="normal badge, pays coins",
            criteria_type=Badge.CriteriaType.FIRST_PROJECT,
            rarity=Badge.Rarity.RARE,
            award_coins=True,
        )
        self.badge_silent = Badge.objects.create(
            name="Silent Badge",
            description="cosmetic badge, no coins",
            criteria_type=Badge.CriteriaType.FIRST_PROJECT,
            rarity=Badge.Rarity.RARE,
            award_coins=False,
        )

    def _start_balance(self) -> Decimal:
        return CoinService.get_balance(self.user)

    def test_award_coins_true_pays_rarity_amount(self) -> None:
        before = self._start_balance()
        BadgeService._award_badge_coins(self.user, self.badge_paying)
        after = self._start_balance()
        self.assertGreater(
            after, before,
            "paying badge should credit coins when award_coins=True",
        )
        # And a BADGE_BONUS ledger row landed
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.user, reason=CoinLedger.Reason.BADGE_BONUS,
            ).exists()
        )

    def test_award_coins_false_skips_payout(self) -> None:
        before = self._start_balance()
        BadgeService._award_badge_coins(self.user, self.badge_silent)
        after = self._start_balance()
        self.assertEqual(
            before, after,
            "silent badge must NOT credit coins when award_coins=False",
        )
        self.assertFalse(
            CoinLedger.objects.filter(
                user=self.user, reason=CoinLedger.Reason.BADGE_BONUS,
            ).exists()
        )


class QuestCompletionAwardsBadgeTests(TestCase):
    """End-to-end: complete a quest → matching QUEST_COMPLETED badge earned."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="e2e-qc", password="pw", role="child",
        )

    def _make_quest(self, *, name: str, xp_reward: int = 0) -> QuestDefinition:
        return QuestDefinition.objects.create(
            name=name,
            description="...",
            quest_type="collection",
            target_value=1,
            duration_days=1,
            xp_reward=xp_reward,
            coin_reward=0,
        )

    def _make_badge(
        self, *, quest_name: str, rarity: str = Badge.Rarity.RARE,
        award_coins: bool = False,
    ) -> Badge:
        return Badge.objects.create(
            name=f"Completed: {quest_name}",
            description=f"awarded for completing {quest_name}",
            criteria_type=Badge.CriteriaType.QUEST_COMPLETED,
            criteria_value={"quest_name": quest_name},
            rarity=rarity,
            award_coins=award_coins,
        )

    def test_quest_completion_with_xp_awards_matching_badge(self) -> None:
        # xp_reward > 0 → AwardService.grant runs evaluate_badges
        qdef = self._make_quest(name="Seven Nights of Stories", xp_reward=50)
        badge = self._make_badge(quest_name="Seven Nights of Stories")

        quest = QuestService.start_quest(self.user, qdef.pk)
        # Force completion via record_progress
        QuestService.record_progress(self.user, "chore_complete")

        quest.refresh_from_db()
        self.assertEqual(quest.status, Quest.Status.COMPLETED)
        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge).exists(),
            "Completing a quest with xp_reward > 0 should award the "
            "QUEST_COMPLETED badge via AwardService.grant.",
        )

    def test_quest_completion_without_xp_still_awards_badge(self) -> None:
        # xp_reward == 0 → badge eval must still run (the xp==0 else branch)
        qdef = self._make_quest(name="Defeat the Doomscroll", xp_reward=0)
        badge = self._make_badge(quest_name="Defeat the Doomscroll")

        QuestService.start_quest(self.user, qdef.pk)
        QuestService.record_progress(self.user, "chore_complete")

        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge).exists(),
            "Completing a quest with xp_reward == 0 should STILL award the "
            "QUEST_COMPLETED badge (direct BadgeService.evaluate_badges call).",
        )

    def test_quest_completion_does_not_award_unrelated_badges(self) -> None:
        qdef = self._make_quest(name="Specific Quest", xp_reward=50)
        badge = self._make_badge(quest_name="Completely Different Quest")

        QuestService.start_quest(self.user, qdef.pk)
        QuestService.record_progress(self.user, "chore_complete")

        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge).exists(),
            "Badge for a different quest name must not be awarded.",
        )
