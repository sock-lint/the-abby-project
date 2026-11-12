"""Parent participation uses the same real payout serialization as children."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementSession, MovementType, MovementTypeSkillTag
from apps.quests.activity import record_activity
from apps.quests.models import ChallengeActivity, ChallengeContribution, ChallengeOccurrence, DailyBonus, QuestDefinition, QuestSkillTag
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ParentPersonalPayoutConcurrencyTests(TransactionTestCase):
    def setUp(self):
        household = make_family("Parent payout race", parents=[{"username": "race-personal-parent"}],
                                children=[{"username": "race-personal-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        category = SkillCategory.objects.create(name="Parent race skill category")
        self.skill = Skill.objects.create(name="Parent persistence", category=category)
        self.movement = MovementType.objects.create(name="Parent race walk", slug="parent-race-walk")
        MovementTypeSkillTag.objects.create(movement_type=self.movement, skill=self.skill)
        self.definition = QuestDefinition.objects.create(
            name="Two personal efforts", description="Parent's own saved work", is_system=True, quest_type="collection",
            target_value=2, duration_days=7, coin_reward=7, xp_reward=12,
            trigger_filter={"allowed_triggers": ["movement_session"]},
        )
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)

    def session(self, minutes):
        return MovementSession.objects.create(user=self.parent, movement_type=self.movement,
                                             duration_minutes=minutes, intensity="medium", occurred_on=timezone.localdate())

    def race(self, source_ids):
        client = APIClient()
        client.force_authenticate(self.parent)
        self.assertEqual(client.get("/api/challenges/", HTTP_X_ABBY_SPACE="personal").status_code, 200)
        barrier = Barrier(2)

        def worker(source_id):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                actor = get_user_model().objects.get(pk=self.parent.pk)
                barrier.wait(timeout=5)
                return record_activity(actor, "movement_session", {"session_id": source_id})
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, source_id) for source_id in source_ids]
            [future.result(timeout=15) for future in futures]
        occurrence = ChallengeOccurrence.objects.get(goal__user=self.parent)
        self.assertEqual((occurrence.status, occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]),
                         ("completed", 7, 12))
        self.assertEqual(DailyBonus.objects.get(user=self.parent).coins_awarded, 10)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, description="Challenge complete: Two personal efforts").count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, reason="daily_challenge").count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 32)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_concurrent_distinct_parent_sources_complete_goal_and_daily_bonus_once(self):
        # Enrollment must precede both accepted source timestamps.
        client = APIClient()
        client.force_authenticate(self.parent)
        client.get("/api/challenges/", HTTP_X_ABBY_SPACE="personal")
        sources = [self.session(5), self.session(5)]
        self.race([source.pk for source in sources])
        self.assertEqual(ChallengeContribution.objects.filter(occurrence__goal__user=self.parent).count(), 2)

    def test_concurrent_parent_source_replay_retains_one_fact_and_each_payout(self):
        self.definition.target_value = 1
        self.definition.save(update_fields=["target_value"])
        client = APIClient()
        client.force_authenticate(self.parent)
        client.get("/api/challenges/", HTTP_X_ABBY_SPACE="personal")
        source = self.session(10)
        self.race([source.pk, source.pk])
        self.assertEqual(ChallengeActivity.objects.filter(user=self.parent).count(), 1)
        self.assertEqual(ChallengeContribution.objects.filter(occurrence__goal__user=self.parent).count(), 1)
