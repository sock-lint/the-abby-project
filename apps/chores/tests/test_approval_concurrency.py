"""Accepted approvals must precede a concurrent first challenge enrollment."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.homework.services import HomeworkService
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeEnrollment, ChallengeOccurrence, QuestDefinition
from apps.rewards.models import CoinLedger
from config.services import finalize_decision
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class FirstApprovalChallengeCreditConcurrencyTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "First approval credit",
            parents=[{"username": "first-credit-parent"}],
            children=[{"username": "first-credit-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]

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

    def _race_first_read(self, source, approve, module, trigger):
        definition = QuestDefinition.objects.create(
            name=f"First {trigger} credit", is_system=True, quest_type="collection",
            target_value=1, coin_reward=7,
            trigger_filter={"allowed_triggers": [trigger]},
        )
        accepted, release = Event(), Event()
        reader_pids = []

        def pause_after_acceptance(*args, **kwargs):
            result = finalize_decision(*args, **kwargs)
            accepted.set()
            if not release.wait(10):
                raise TimeoutError("Approval was not released")
            return result

        with patch(f"{module}.finalize_decision", pause_after_acceptance), ThreadPoolExecutor(max_workers=2) as pool:
            approval_future = pool.submit(self._worker, approve)
            reader_future = None
            try:
                self.assertTrue(accepted.wait(5), "Approval did not reach its accepted timestamp")
                reader_future = pool.submit(self._worker, lambda: list_goals(self.child), reader_pids)
                # Wait for a real ordering boundary: the reader either finishes
                # ahead of the approval (the bug), or waits on its account lock.
                deadline, reached_boundary = monotonic() + 5, False
                while monotonic() < deadline:
                    if reader_future.done():
                        reader_future.result()
                        reached_boundary = True
                        break
                    if reader_pids:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                                [reader_pids[0]],
                            )
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            reached_boundary = True
                            break
                    sleep(0.01)
                self.assertTrue(reached_boundary, "Challenge reader neither completed nor reached a database lock")
            finally:
                release.set()
            approval_future.result(timeout=15)
            if reader_future:
                reader_future.result(timeout=15)

        source.refresh_from_db()
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.starts_at, occurrence.progress, occurrence.status),
                         (source.decided_at, 1, "completed"))
        self.assertEqual(ChallengeEnrollment.objects.get(user=self.child).starts_at, source.decided_at)
        self.assertIsNotNone(occurrence.awarded_at)
        self.assertEqual(CoinLedger.objects.filter(
            user=self.child, amount=7, description=f"Challenge complete: {definition.name}",
        ).count(), 1)

    def test_first_approved_chore_keeps_credit_during_initial_catalog_read(self):
        chore = Chore.objects.create(title="First chore", created_by=self.parent, family=self.parent.family)
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child, completed_date=timezone.localdate(),
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )
        self._race_first_read(
            completion, lambda: ChoreService.approve_completion(completion, self.parent),
            "apps.chores.services", "chore_complete",
        )

    def test_first_approved_homework_keeps_credit_during_initial_catalog_read(self):
        assignment = HomeworkAssignment.objects.create(
            title="First homework", subject="math", due_date=timezone.localdate(),
            assigned_to=self.child, created_by=self.parent,
        )
        submission = HomeworkSubmission.objects.create(
            assignment=assignment, user=self.child, timeliness="on_time",
        )
        self._race_first_read(
            submission, lambda: HomeworkService.approve_submission(submission, self.parent),
            "apps.homework.services", "homework_complete",
        )
