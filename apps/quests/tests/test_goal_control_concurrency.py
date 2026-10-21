"""Retry and schedule writes share the real PostgreSQL account gate."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.quests.controls import retry_challenge, update_schedule
from apps.quests.goals import create_goal, ingest_activity, list_goals
from apps.quests.models import ChallengeOccurrence, ChallengeSchedule, QuestDefinition
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class GoalControlConcurrencyTests(TransactionTestCase):
    def setUp(self):
        household = make_family("Control races", parents=[{"username": "race-parent"}, {"username": "race-coparent"}],
                                children=[{"username": "race-child"}])
        self.parent, self.coparent = household.parents
        self.child = household.children[0]
        self.now = timezone.now()
        self.start = self.now - timedelta(days=10)
        with patch("django.utils.timezone.now", return_value=self.start):
            self.definition = QuestDefinition.objects.create(
                name="Race attempt", quest_type="collection", target_value=2, duration_days=2,
                is_system=True, coin_reward=7, trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            list_goals(self.child)
        self.original = ChallengeOccurrence.objects.get(goal__user=self.child)

    def race(self, actions):
        barrier = Barrier(len(actions))

        def run(action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                try:
                    return action()
                except ValueError as error:
                    return str(error)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            return [future.result(timeout=20) for future in [pool.submit(run, action) for action in actions]]

    def test_two_retry_requests_create_the_same_successor(self):
        results = self.race([lambda: retry_challenge(self.child, self.original.pk)] * 2)
        self.assertEqual({result[0].pk for result in results},
                         {ChallengeOccurrence.objects.get(retry_of=self.original).pk})
        self.assertEqual(sum(result[1] for result in results), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_late_old_completion_and_retry_completion_pay_one_lifetime_reward(self):
        ingest_activity(self.child, "chore_complete", "old-first", "chore_complete", occurred_at=self.start)
        successor, _ = retry_challenge(self.child, self.original.pk)
        ingest_activity(self.child, "chore_complete", "new-first", "chore_complete", occurred_at=successor.starts_at)
        self.race([
            lambda: ingest_activity(self.child, "chore_complete", "old-final", "chore_complete", occurred_at=self.start),
            lambda: ingest_activity(self.child, "chore_complete", "new-final", "chore_complete", occurred_at=successor.starts_at),
        ])
        self.assertEqual(ChallengeOccurrence.objects.filter(status="completed").count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.filter(status="closed", awarded_at__isnull=True).count(), 1)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [7])

    def test_late_completion_racing_retry_acceptance_never_creates_an_extra_reward(self):
        ingest_activity(self.child, "chore_complete", "old-first", "chore_complete", occurred_at=self.start)
        self.race([
            lambda: retry_challenge(self.child, self.original.pk),
            lambda: ingest_activity(self.child, "chore_complete", "old-final", "chore_complete", occurred_at=self.start),
        ])
        self.assertEqual(ChallengeOccurrence.objects.filter(status="completed").count(), 1)
        self.assertFalse(ChallengeOccurrence.objects.filter(status="active").exists())
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_two_parent_edits_at_one_revision_have_one_winner(self):
        row = create_goal(self.parent, self.child, {
            "name": "Weekly race", "metric": "count", "target": Decimal(2), "unit": "actions",
            "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
        })
        results = self.race([
            lambda: update_schedule(self.parent, row.goal_id, {"expected_revision": 0, "next_week": {"target": 3}}),
            lambda: update_schedule(self.coparent, row.goal_id, {"expected_revision": 0, "paused": True}),
        ])
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, str) for result in results), 1)
        row.goal.refresh_from_db()
        self.assertEqual(row.goal.schedule_revision, 1)
        self.assertEqual(ChallengeSchedule.objects.count(), 1)
