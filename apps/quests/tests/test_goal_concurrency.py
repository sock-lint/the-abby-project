"""Goal payout races require real PostgreSQL user-row serialization."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeActivity, ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestSkillTag
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class GoalConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="goal-race", role="child")
        self.at = timezone.now()
        ChallengeEnrollment.objects.create(user=self.user, starts_at=self.at - timedelta(hours=1))
        category = SkillCategory.objects.create(name="Goal concurrency")
        self.skill = Skill.objects.create(name="Effort", category=category)
        definition = QuestDefinition.objects.create(
            name="Two chores", description="Approved chores", is_system=True, quest_type="collection",
            target_value=2, duration_days=7, coin_reward=5, xp_reward=10,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
        ingest_activity(self.user, "chore_complete", "first", "chore_complete", occurred_at=self.at)

    def _race(self, identities):
        barrier = Barrier(2)

        def worker(identity):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                user = get_user_model().objects.get(pk=self.user.pk)
                return ingest_activity(user, "chore_complete", identity, "chore_complete", occurred_at=self.at)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, identity) for identity in identities]
            results = [future.result(timeout=15) for future in futures]
        occurrence = ChallengeOccurrence.objects.get()
        self.assertEqual((occurrence.status, occurrence.progress), ("completed", 2))
        self.assertEqual(CoinLedger.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.user, skill=self.skill).xp_points, 10)
        self.assertEqual(sum(len(result["goals"]) for result in results), 1)

    def test_concurrent_final_contributions_award_once(self):
        self._race(["second", "third"])

    def test_duplicate_final_source_has_one_fact_and_one_payout(self):
        self._race(["second", "second"])
        self.assertEqual(ChallengeActivity.objects.filter(user=self.user).count(), 2)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class LegacyEnrollmentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="legacy-enrollment", role="child")
        self.other = get_user_model().objects.create_user(username="legacy-coop", role="child", family=self.user.family)
        self.definition = QuestDefinition.objects.create(
            name="Legacy enrollment race", description="One reward owner", is_system=True,
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )

    @staticmethod
    def _worker(action, pids=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                if pids is not None:
                    pids.append(cursor.fetchone()[0])
            return action()
        finally:
            connection.close()

    def _overlap_legacy_start_and_enrollment(self, *, co_op):
        reached_create, release = Event(), Event()
        original_create = Quest.objects.create
        enrollment_pids = []

        def hold_legacy_create(*args, **kwargs):
            reached_create.set()
            if not release.wait(10):
                raise TimeoutError("Legacy create was not released")
            return original_create(*args, **kwargs)

        def legacy():
            if co_op:
                # Deliberately reversed input: locks must follow sorted user IDs.
                return QuestService.start_co_op_quest(self.definition.pk, [self.other, self.user])
            return QuestService.start_quest(self.user, self.definition.pk)

        with patch.object(Quest.objects, "create", hold_legacy_create), ThreadPoolExecutor(max_workers=2) as pool:
            legacy_future = pool.submit(self._worker, legacy)
            enrollment_future = None
            try:
                self.assertTrue(reached_create.wait(5))
                enrollment_future = pool.submit(self._worker, lambda: list_goals(self.user), enrollment_pids)
                deadline, blocked = monotonic() + 5, False
                while monotonic() < deadline:
                    if enrollment_future.done():
                        enrollment_future.result()
                        break
                    if enrollment_pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [enrollment_pids[0]])
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            blocked = True
                            break
                    sleep(0.01)
                self.assertTrue(blocked, "Automatic enrollment bypassed the legacy user's lock")
            finally:
                release.set()
            legacy_future.result(timeout=15)
            if enrollment_future:
                enrollment_future.result(timeout=15)
        self.assertTrue(Quest.objects.filter(definition=self.definition, participants__user=self.user, status="active").exists())
        self.assertFalse(ChallengeGoal.objects.filter(user=self.user, catalog_definition=self.definition).exists())

    def test_single_legacy_start_serializes_automatic_enrollment(self):
        self._overlap_legacy_start_and_enrollment(co_op=False)

    def test_coop_legacy_start_serializes_automatic_enrollment(self):
        self._overlap_legacy_start_and_enrollment(co_op=True)
