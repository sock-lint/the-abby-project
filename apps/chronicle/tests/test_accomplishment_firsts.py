"""Completed accomplishments reach Yearbook without replaying their rewards."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.movement.services import MovementSessionService
from apps.notifications.models import Notification
from apps.quests.goals import ingest_activity
from apps.quests.models import ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.quests.tests.test_goals import _GoalFixture
from apps.rewards.services import CoinService
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, PerfectDayReceipt
from apps.rpg.services import DropService
from apps.rpg.tasks import evaluate_perfect_day_task
from apps.rpg.tests.test_accomplishment_drops import AccomplishmentDropFixture


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class AccomplishmentFirstTests(AccomplishmentDropFixture, TestCase):
    def assert_first(self, slug):
        self.assertEqual(ChronicleEntry.objects.filter(
            user=self.child, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug=slug,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            user=self.child, notification_type="chronicle_first_ever",
        ).count(), 1)

    def legendary_badge(self):
        badge = self.badge()
        badge.rarity = Badge.Rarity.LEGENDARY
        badge.save(update_fields=["rarity"])
        return badge

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_legendary_badge_first_and_drop_are_once_only(self, _roll):
        badge = self.legendary_badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        BadgeService.evaluate_badges(self.child, scopes={"chore"})
        BadgeService.evaluate_badges(self.child, scopes={"chore"})

        self.assert_first("first_legendary_badge")
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assertEqual(CoinService.get_balance(self.child), 0)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_perfect_day_first_preserves_one_uncommon_drop_and_bonus(self, _roll):
        self.seed_drop(TriggerType.PERFECT_DAY)

        evaluate_perfect_day_task()
        evaluate_perfect_day_task()

        self.assert_first("first_perfect_day")
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child).count(), 1)
        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.assertEqual(DropLog.objects.get(user=self.child).item.rarity, "uncommon")
        self.assertEqual(CoinService.get_balance(self.child), 15)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_legacy_quest_first_preserves_completion_payout_and_replay(self, _roll):
        definition = QuestDefinition.objects.create(
            name="Finish a duty", quest_type="collection", target_value=1,
            coin_reward=7, created_by=self.parent,
        )
        quest = Quest.objects.create(
            definition=definition, end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.seed_drop(TriggerType.QUEST_COMPLETE)

        QuestService.record_progress(self.child, TriggerType.CHORE_COMPLETE)
        QuestService.record_progress(self.child, TriggerType.CHORE_COMPLETE)

        self.assert_first("first_quest_completed")
        quest.refresh_from_db()
        self.assertEqual(quest.status, Quest.Status.COMPLETED)
        self.assert_single_drop(TriggerType.QUEST_COMPLETE)
        self.assertEqual(CoinService.get_balance(self.child), 7)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 0)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_first_failure_rolls_back_only_recognition_not_badge_or_loot(self, _roll):
        badge = self.legendary_badge()
        self.seed_drop(TriggerType.BADGE_EARNED)
        original = ChronicleService.record_first

        def fail_after_first(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("Yearbook unavailable")

        with patch.object(ChronicleService, "record_first", side_effect=fail_after_first) as writer:
            BadgeService.evaluate_badges(self.child, scopes={"chore"})

        writer.assert_called_once()
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(
            user=self.child, notification_type="chronicle_first_ever",
        ).exists())

    def test_historical_accomplishments_are_not_backfilled_by_replays(self):
        badge = self.legendary_badge()
        UserBadge.objects.create(user=self.child, badge=badge)
        PerfectDayReceipt.objects.create(user=self.child, day=self.day, historical=True)

        BadgeService.evaluate_badges(self.child, scopes={"chore"})
        evaluate_perfect_day_task()

        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(
            user=self.child, notification_type="chronicle_first_ever",
        ).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_failed_queued_milestone_badge_keeps_original_legendary_badge(self, _roll):
        for index in range(2):
            ChronicleEntry.objects.create(
                user=self.child, kind=ChronicleEntry.Kind.FIRST_EVER,
                event_slug=f"prior-{index}", title="Earlier first",
                occurred_on=self.day, chapter_year=self.day.year,
            )
        milestone = Badge.objects.create(
            name="Turning Point", criteria_type=Badge.CriteriaType.CHRONICLE_MILESTONES_LOGGED,
            criteria_value={"count": 3}, xp_bonus=0, award_coins=False,
        )
        legendary = self.legendary_badge()
        self.seed_drop(TriggerType.BADGE_EARNED)
        original = DropService.award_accomplishment

        def fail_milestone_drop(user, trigger):
            if UserBadge.objects.filter(user=user, badge=milestone).exists():
                raise RuntimeError("Milestone payout unavailable")
            return original(user, trigger)

        with patch.object(DropService, "award_accomplishment", side_effect=fail_milestone_drop):
            BadgeService.evaluate_badges(self.child, scopes={"chore"})

        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=legendary).exists())
        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=milestone).exists())
        self.assertFalse(ChronicleEntry.objects.filter(
            user=self.child, event_slug="first_legendary_badge",
        ).exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class AutomaticQuestFirstTests(_GoalFixture, TestCase):
    def test_real_movement_completion_records_first_without_repaying_on_fact_replay(self):
        definition = self.definition(target=1)
        session = MovementSessionService.log_session(
            self.child, movement_type=self.running, duration_minutes=20,
        )
        before_coins = CoinService.get_balance(self.child)
        before_drops = DropLog.objects.filter(user=self.child).count()

        ingest_activity(
            self.child, "movement_session", session.pk, "movement_session",
            occurred_at=session.created_at,
            context={"movement_type_id": self.running.pk, "duration_minutes": 20},
        )

        self.assertEqual(ChronicleEntry.objects.filter(
            user=self.child, event_slug="first_quest_completed",
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            user=self.child, notification_type="chronicle_first_ever",
        ).count(), 1)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))
        self.assertIsNotNone(occurrence.awarded_at)
        self.assertEqual(CoinService.get_balance(self.child), before_coins)
        self.assertEqual(DropLog.objects.filter(user=self.child).count(), before_drops)
