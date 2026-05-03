"""Endpoint tests for GET /api/dashboard/.

Currently covers only the `next_actions` field added for the priority feed.
Other dashboard fields are covered implicitly by the pages that consume them."""
import datetime
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.timecards.models import Timecard
from config.tests.factories import make_family


class DashboardNextActionsTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent")
        self.child = User.objects.create_user(
            username="c", password="pw", role="child")
        self.client = APIClient()

    def test_parent_receives_empty_next_actions(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["next_actions"], [])
        self.assertEqual(data["newly_unlocked_lorebook"], [])

    def test_child_receives_scored_next_actions(self):
        HomeworkAssignment.objects.create(
            title="Math workbook", subject="math", effort_level=3,
            due_date=datetime.date.today() + datetime.timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        Chore.objects.create(
            title="Clean Room", recurrence="weekly",
            reward_amount=Decimal("1.00"), coin_reward=2,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("next_actions", data)
        self.assertGreaterEqual(len(data["next_actions"]), 2)
        first = data["next_actions"][0]
        required_keys = {
            "kind", "id", "title", "subtitle", "score",
            "due_at", "reward", "icon", "tone", "action_url",
        }
        self.assertTrue(required_keys <= set(first.keys()))
        # Homework due tomorrow (60) outranks weekly chore on any weekday (≤58)
        self.assertEqual(first["kind"], "homework")

    def test_child_item_shape_for_chore(self):
        Chore.objects.create(
            title="Dishes", icon="🍽", recurrence="daily",
            reward_amount=Decimal("0.50"), coin_reward=1,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        data = self.client.get("/api/dashboard/").json()
        chore_item = next(
            (a for a in data["next_actions"] if a["kind"] == "chore"), None,
        )
        self.assertIsNotNone(chore_item)
        self.assertEqual(chore_item["reward"], {"money": "0.50", "coins": 1})
        self.assertEqual(chore_item["tone"], "moss")
        self.assertEqual(chore_item["action_url"], "/chores")
        self.assertIsNone(chore_item["due_at"])

    def test_newly_unlocked_lorebook_excludes_seen_flags(self):
        CoinLedger.objects.create(
            user=self.child,
            amount=5,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description="seed",
            created_by=self.parent,
        )
        self.child.lorebook_flags = {"coins_seen": True}
        self.child.save(update_fields=["lorebook_flags"])

        self.client.force_authenticate(self.child)
        data = self.client.get("/api/dashboard/").json()
        self.assertIn("newly_unlocked_lorebook", data)
        self.assertNotIn("coins", data["newly_unlocked_lorebook"])

    def test_newly_unlocked_lorebook_includes_unseen_unlocks(self):
        CoinLedger.objects.create(
            user=self.child,
            amount=5,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description="seed",
            created_by=self.parent,
        )

        self.client.force_authenticate(self.child)
        data = self.client.get("/api/dashboard/").json()
        self.assertIn("coins", data["newly_unlocked_lorebook"])

    def test_parent_receives_no_new_lorebook_unlocks(self):
        self.client.force_authenticate(self.parent)
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(data["newly_unlocked_lorebook"], [])


class DashboardParentPendingFamilyScopingTests(TestCase):
    """Audit C3: parent's pending_timecards / pending_chore_approvals counts
    must be scoped to the parent's family, not aggregated across the whole
    deployment.
    """

    def setUp(self):
        self.fam_a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.fam_b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.parent_a = self.fam_a.parents[0]
        self.kid_a = self.fam_a.children[0]
        self.kid_b = self.fam_b.children[0]
        self.client = APIClient()

    def test_pending_chore_approvals_excludes_other_families(self):
        chore_a = Chore.objects.create(
            title="Trash A", recurrence="daily",
            assigned_to=self.kid_a, created_by=self.parent_a,
        )
        chore_b = Chore.objects.create(
            title="Trash B", recurrence="daily",
            assigned_to=self.kid_b, created_by=self.fam_b.parents[0],
        )
        ChoreCompletion.objects.create(
            chore=chore_a, user=self.kid_a,
            status=ChoreCompletion.Status.PENDING,
            completed_date=datetime.date.today(),
            reward_amount_snapshot=Decimal("0.00"),
            coin_reward_snapshot=0,
        )
        ChoreCompletion.objects.create(
            chore=chore_b, user=self.kid_b,
            status=ChoreCompletion.Status.PENDING,
            completed_date=datetime.date.today(),
            reward_amount_snapshot=Decimal("0.00"),
            coin_reward_snapshot=0,
        )

        self.client.force_authenticate(self.parent_a)
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(data["pending_chore_approvals"], 1)

    def test_pending_timecards_excludes_other_families(self):
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
        Timecard.objects.create(
            user=self.kid_a,
            week_start=week_start,
            week_end=week_start + datetime.timedelta(days=6),
            status="pending",
        )
        Timecard.objects.create(
            user=self.kid_b,
            week_start=week_start,
            week_end=week_start + datetime.timedelta(days=6),
            status="pending",
        )

        self.client.force_authenticate(self.parent_a)
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(data["pending_timecards"], 1)
