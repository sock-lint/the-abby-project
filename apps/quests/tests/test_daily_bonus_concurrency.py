"""The old daily client and factual bonus share one PostgreSQL payout lock."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory
from apps.movement.models import MovementSession, MovementType, MovementTypeSkillTag
from apps.quests.activity import household_timezone, record_activity
from apps.quests.models import DailyBonus
from apps.quests.services import DailyChallengeService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class DailyBonusConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family("Daily concurrency", children=[{"username": "daily-race"}]).children[0]
        category = SkillCategory.objects.create(name="Daily concurrency skills")
        skill = Skill.objects.create(name="Persistence", category=category)
        self.movement = MovementType.objects.create(name="Daily run", slug="daily-race")
        MovementTypeSkillTag.objects.create(movement_type=self.movement, skill=skill)

    def session(self, minutes):
        return MovementSession.objects.create(
            user=self.child, movement_type=self.movement, duration_minutes=minutes, intensity="medium",
            occurred_on=timezone.localdate(timezone.now(), timezone=household_timezone(self.child)),
        )

    def race(self, callbacks):
        barrier = Barrier(2)

        def worker(callback):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return callback()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, callback) for callback in callbacks]
            return [future.result(timeout=15) for future in futures]

    def test_two_short_final_sessions_pay_once(self):
        sessions = [self.session(5), self.session(5)]
        results = self.race([
            lambda source=source: record_activity(self.child, "movement_session", {"session_id": source.pk})
            for source in sessions
        ])
        self.assertEqual(DailyBonus.objects.get(user=self.child).coins_awarded, 10)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
        self.assertEqual(sum(bool(result["daily_bonus"]) for result in results), 1)

    def test_legacy_get_overlapping_new_award_cannot_create_another_payout(self):
        source = self.session(10)
        self.race([
            lambda: DailyChallengeService.get_or_create_today(self.child),
            lambda: record_activity(self.child, "movement_session", {"session_id": source.pk}),
        ])
        self.assertIsNotNone(DailyBonus.objects.get(user=self.child).awarded_at)
        self.assertTrue(DailyChallengeService.claim_reward(self.child)["already_claimed"])
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)
