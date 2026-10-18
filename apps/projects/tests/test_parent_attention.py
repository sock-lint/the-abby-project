from django.test import TestCase
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from apps.chores.models import Chore
from apps.projects.parent_attention import parent_attention
from apps.rewards.models import Reward, RewardRedemption
from apps.timecards.models import Timecard
from config.tests.factories import make_family


class ParentAttentionTests(TestCase):
    def setUp(self):
        self.home = make_family("Attention", parents=[{"username": "parent"}], children=[{"username": "kid"}])
        self.other = make_family("Other", parents=[{"username": "other"}], children=[{"username": "other-kid"}])

    def test_counts_deliveries_proposals_and_disputed_cards_without_foreign_rows(self):
        kid = self.home.children[0]
        reward = Reward.objects.create(family=self.home.family, name="Outing", cost_coins=10)
        RewardRedemption.objects.create(user=kid, reward=reward, coin_cost_snapshot=10, status="approved")
        Chore.objects.create(created_by=self.home.children[0], family=self.home.family, title="Proposed", pending_parent_review=True)
        Timecard.objects.create(user=kid, week_start="2026-10-12", week_end="2026-10-18", status="disputed")
        Chore.objects.create(created_by=self.other.children[0], family=self.other.family, title="Other proposal", pending_parent_review=True)
        data = parent_attention(self.home.parents[0])
        self.assertEqual(data["counts"]["deliveries"], 1)
        self.assertEqual(data["counts"]["timecards"], 1)
        self.assertEqual(data["counts"]["chore_proposals"], 1)
        self.assertEqual(data["total"], 3)
        self.assertNotIn("Outing", str(data))

    def test_same_count_with_a_new_request_changes_revision(self):
        chore = Chore.objects.create(created_by=self.home.children[0], family=self.home.family, title="First", pending_parent_review=True)
        before = parent_attention(self.home.parents[0])
        chore.delete()
        Chore.objects.create(created_by=self.home.children[0], family=self.home.family, title="Next", pending_parent_review=True)
        after = parent_attention(self.home.parents[0])
        self.assertEqual(before["counts"], after["counts"])
        self.assertNotEqual(before["revision"], after["revision"])

    def test_child_has_no_parent_signal(self):
        self.assertIsNone(parent_attention(self.home.children[0]))

    def test_household_midnight_changes_revision_without_a_new_request(self):
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 6, 59, tzinfo=datetime_timezone.utc)):
            before = parent_attention(self.home.parents[0])
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 7, 1, tzinfo=datetime_timezone.utc)):
            after = parent_attention(self.home.parents[0])
        self.assertEqual(before["counts"], after["counts"])
        self.assertNotEqual(before["revision"], after["revision"])

    def test_co_parent_name_and_rate_edits_refresh_the_overview(self):
        before = parent_attention(self.home.parents[0])
        child = self.home.children[0]
        child.display_name = "Updated child name"
        child.hourly_rate = "12.00"
        child.save(update_fields=["display_name", "hourly_rate"])
        after = parent_attention(self.home.parents[0])
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertNotIn("Updated child name", after["revision"])

    def test_recurring_goal_boundary_refreshes_within_the_household_day(self):
        from apps.quests.models import ChallengeGoal

        ChallengeGoal.objects.create(
            family=self.home.family, created_by=self.home.parents[0], user=self.home.children[0],
            name="Private goal name", metric="minutes", target=20, unit="minutes",
            starts_at=datetime(2026, 10, 14, 22, tzinfo=datetime_timezone.utc),
            ends_at=datetime(2026, 10, 17, 22, tzinfo=datetime_timezone.utc),
            repeat_days=3, timezone_name="America/New_York",
        )
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 17, 21, 59, tzinfo=datetime_timezone.utc)):
            before = parent_attention(self.home.parents[0])
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 17, 22, 1, tzinfo=datetime_timezone.utc)):
            after = parent_attention(self.home.parents[0])
        self.assertEqual(before["counts"], after["counts"])
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertNotIn("Private goal name", after["revision"])

    def test_query_count_is_bounded(self):
        with self.assertNumQueries(18):
            parent_attention(self.home.parents[0])
