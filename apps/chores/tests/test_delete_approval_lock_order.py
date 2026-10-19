"""Deleting a chore and approving its pending completion must not deadlock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.quests import goals
from apps.quests.models import ChallengeActivity
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ChoreDeleteApprovalLockOrderTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "Chore delete lock order",
            parents=[{"username": "delete-order-parent"}, {"username": "delete-order-coparent"}],
            children=[{"username": "delete-order-child"}],
        )
        self.parent, self.coparent = household.parents
        self.child = household.children[0]
        self.chore = Chore.objects.create(
            title="Feed the fish", reward_amount=Decimal("1.00"), coin_reward=2,
            recurrence="daily", created_by=self.parent, family=household.family,
        )
        today = timezone.localdate()
        approved = ChoreCompletion.objects.create(
            chore=self.chore, user=self.child, completed_date=today - timedelta(days=1),
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=self.chore.reward_amount, coin_reward_snapshot=self.chore.coin_reward,
        )
        # An approved completion's challenge fact makes the cascade void it,
        # which locks the child after the completions are deleted.
        ChallengeActivity.objects.create(
            user=self.child, source_type="chore_complete", source_id=str(approved.pk),
            trigger_type="chore_complete", occurred_at=timezone.now(), occurred_on=today,
        )
        self.pending = ChoreCompletion.objects.create(
            chore=self.chore, user=self.child, completed_date=today,
            reward_amount_snapshot=self.chore.reward_amount, coin_reward_snapshot=self.chore.coin_reward,
        )

    @staticmethod
    def _request(user, method, path, pids):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
            client = APIClient(raise_request_exception=False)
            client.force_authenticate(user)
            return getattr(client, method)(path, format="json").status_code
        finally:
            connection.close()

    def _blocked(self, pid):
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
            return cursor.fetchone()[0]

    def test_approval_waits_for_delete_cascade_instead_of_deadlocking(self):
        voiding, release = Event(), Event()
        original = goals.void_activity

        def pause_while_voiding(*args, **kwargs):
            voiding.set()
            if not release.wait(10):
                raise TimeoutError("Delete was not released")
            return original(*args, **kwargs)

        delete_pids, approve_pids = [], []
        with patch("apps.quests.goals.void_activity", side_effect=pause_while_voiding), \
                ThreadPoolExecutor(max_workers=2) as pool:
            delete = pool.submit(self._request, self.parent, "delete", f"/api/chores/{self.chore.pk}/", delete_pids)
            self.assertTrue(voiding.wait(10), "The cascade did not reach the challenge voiding step")
            approve = pool.submit(
                self._request, self.coparent, "post", f"/api/chore-completions/{self.pending.pk}/approve/", approve_pids,
            )
            deadline = monotonic() + 10
            while (not approve_pids or not self._blocked(approve_pids[0])) and not approve.done() and monotonic() < deadline:
                sleep(0.05)
            release.set()
            self.assertEqual(delete.result(timeout=20), 204)
            self.assertEqual(approve.result(timeout=20), 404)
        self.assertFalse(Chore.objects.filter(pk=self.chore.pk).exists())
        self.assertTrue(ChallengeActivity.objects.get(source_id__isnull=False, user=self.child).voided)
