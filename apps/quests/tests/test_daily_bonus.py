from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementType, MovementTypeSkillTag
from apps.movement.services import MovementSessionService
from apps.quests.activity import retry_pending_activity
from apps.quests.daily_bonus import get_daily_bonus_payload, settle_legacy_bonuses
from apps.quests.models import ChallengeActivity, DailyBonus, DailyChallenge
from apps.quests.tasks import rotate_daily_challenges_task
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class AutomaticDailyBonusTests(TestCase):
    def setUp(self):
        family = make_family("Daily bonus", parents=[{"username": "dailyparent"}], children=[{"username": "dailychild"}])
        self.child = family.children[0]
        category = SkillCategory.objects.create(name="Physical")
        self.skill = Skill.objects.create(name="Persistence", category=category)
        self.running = MovementType.objects.create(name="Run", slug="daily-run")
        MovementTypeSkillTag.objects.create(movement_type=self.running, skill=self.skill, xp_weight=1)

    def run_for(self, minutes):
        return MovementSessionService.log_session(self.child, movement_type=self.running, duration_minutes=minutes)

    def test_first_work_earns_bonus_without_opening_today(self):
        self.run_for(10)
        bonus = DailyBonus.objects.get(user=self.child)
        self.assertIsNotNone(bonus.awarded_at)
        self.assertEqual(bonus.coins_awarded, 10)
        self.assertEqual(bonus.xp_awarded, 20)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 25)
        self.assertTrue(get_daily_bonus_payload(self.child)["awarded"])

    def test_short_sessions_accumulate_and_award_once(self):
        self.run_for(5)
        self.assertFalse(DailyBonus.objects.exists())
        self.run_for(5)
        self.run_for(10)
        self.assertEqual(DailyBonus.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
        self.assertEqual(get_daily_bonus_payload(self.child)["progress_minutes"], 20)

    def test_reading_and_rotation_cannot_manufacture_a_bonus(self):
        get_daily_bonus_payload(self.child)
        rotate_daily_challenges_task()
        self.assertEqual(DailyBonus.objects.count(), 0)
        self.assertEqual(DailyChallenge.objects.count(), 0)
        self.assertEqual(CoinLedger.objects.count(), 0)

    def test_claimed_legacy_bonus_cannot_pay_again(self):
        day = timezone.localdate()
        DailyChallenge.objects.create(user=self.child, date=day, challenge_type="habits", target_value=2,
                                      current_progress=2, completed_at=timezone.now(), coin_reward=0, xp_reward=0)
        self.run_for(10)
        bonus = DailyBonus.objects.get(user=self.child)
        self.assertIsNotNone(bonus.awarded_at)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 0)
        self.assertIsNone(get_daily_bonus_payload(self.child)["receipt_id"])

    def test_legacy_get_and_claim_after_new_bonus_cannot_pay_again(self):
        from apps.quests.services import DailyChallengeService
        self.run_for(10)
        legacy = DailyChallengeService.get_or_create_today(self.child)
        self.assertTrue(legacy.is_complete)
        self.assertEqual((legacy.coin_reward, legacy.xp_reward), (0, 0))
        self.assertTrue(DailyChallengeService.claim_reward(self.child)["already_claimed"])
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)

    def test_completed_unclaimed_legacy_bonus_keeps_its_reward_promise(self):
        day = timezone.localdate() - timedelta(days=1)
        legacy = DailyChallenge.objects.create(user=self.child, date=day, challenge_type="chores", target_value=2,
                                               current_progress=2, completed_at=timezone.now(), coin_reward=15, xp_reward=30)
        self.assertEqual(settle_legacy_bonuses(), 1)
        self.assertEqual(settle_legacy_bonuses(), 0)
        bonus = DailyBonus.objects.get(user=self.child, date=day)
        self.assertEqual((bonus.coins_awarded, bonus.xp_awarded), (15, 30))
        legacy.refresh_from_db()
        self.assertEqual((legacy.coin_reward, legacy.xp_reward), (0, 0))

    def test_late_legacy_completions_keep_each_original_date_reward(self):
        for days_ago in (1, 2):
            DailyChallenge.objects.create(
                user=self.child, date=timezone.localdate() - timedelta(days=days_ago),
                challenge_type="chores", target_value=2, current_progress=2,
                completed_at=timezone.now(), coin_reward=15, xp_reward=30,
            )
        self.assertEqual(settle_legacy_bonuses(), 2)
        self.assertEqual(settle_legacy_bonuses(), 0)
        self.assertEqual(list(DailyBonus.objects.values_list("coins_awarded", flat=True)), [15, 15])
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 2)

    def test_processing_failure_keeps_fact_for_bounded_retry(self):
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("temporary")):
            # The base movement reward catches its downstream failure too.
            self.run_for(10)
        fact = ChallengeActivity.objects.get(user=self.child, source_type="movement_session")
        self.assertIsNone(fact.processed_at)
        self.assertFalse(DailyBonus.objects.exists())
        self.assertEqual(retry_pending_activity(self.child), 1)
        fact.refresh_from_db()
        self.assertIsNotNone(fact.processed_at)
        self.assertEqual(fact.context["_receipt"]["daily_bonus"]["coins_awarded"], 10)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
        self.assertEqual(retry_pending_activity(self.child), 0)

    def test_family_local_date_controls_bonus(self):
        self.child.family.timezone = "Pacific/Auckland"
        self.child.family.save(update_fields=["timezone"])
        self.run_for(10)
        self.assertEqual(DailyBonus.objects.get(user=self.child).date,
                         timezone.localdate(timezone.now(), timezone=ZoneInfo("Pacific/Auckland")))

    def test_failed_repair_does_not_starve_another_family(self):
        from apps.quests.daily_bonus import process_daily_bonus
        other = make_family("Other daily", children=[{"username": "other-daily-child"}]).children[0]
        with patch("apps.quests.daily_bonus.process_daily_bonus", side_effect=RuntimeError("temporary")):
            self.run_for(10)
            MovementSessionService.log_session(other, movement_type=self.running, duration_minutes=10)
        self.assertEqual(ChallengeActivity.objects.filter(processed_at__isnull=True).count(), 2)

        def selective_failure(user, activity):
            if user.pk == self.child.pk:
                raise RuntimeError("still pending")
            return process_daily_bonus(user, activity)

        with patch("apps.quests.daily_bonus.process_daily_bonus", side_effect=selective_failure):
            self.assertEqual(retry_pending_activity(), 1)
        self.assertIsNone(ChallengeActivity.objects.get(user=self.child).processed_at)
        self.assertIsNotNone(ChallengeActivity.objects.get(user=other).processed_at)
        self.assertTrue(DailyBonus.objects.filter(user=other, awarded_at__isnull=False).exists())

    def test_deleting_logs_does_not_rearm_paid_daily_bonus(self):
        from apps.quests.goals import void_activity
        session = self.run_for(10)
        void_activity(self.child, "movement_session", session.pk)
        session.delete()
        self.run_for(10)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
