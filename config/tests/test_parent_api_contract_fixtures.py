"""Shared parent dashboard fixture comes from the actual scoped endpoint."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, UserBadge
from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.projects.models import Project
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared_fixtures


FIXED_NOW = datetime(2026, 10, 19, 2, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class ParentApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def test_family_overview_is_the_household_day_with_safe_confirmed_accomplishments(self):
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            household = make_family(
                "Parent Overview Fixture", family_id=61,
                parents=[{"id": 6, "username": "overview-fixture-parent"}],
                children=[
                    {"id": 7, "username": "abby", "display_name": "Abby", "hourly_rate": "10.00"},
                    {"id": 8, "username": "ben", "display_name": "Ben"},
                ],
            )
            parent, child = household.parents[0], household.children[0]
            for title, due in (("Math practice", date(2026, 10, 18)),
                               ("Reading worksheet", date(2026, 10, 17)),
                               ("Science notes", date(2026, 10, 16))):
                assignment = HomeworkAssignment.objects.create(
                    title=title, subject="math", assigned_to=child, created_by=parent,
                    due_date=due, notes="Synthetic private parent context, never in the overview.",
                )
                if title == "Science notes":
                    HomeworkSubmission.objects.create(
                        assignment=assignment, user=child, status="pending", timeliness="late",
                        notes="Synthetic private submission body, never in the overview.",
                    )
            Chore.objects.create(title="Tidy up", family=household.family, created_by=parent)
            chore = Chore.objects.create(
                title="Make the bed", family=household.family, created_by=parent, assigned_to=child,
            )
            ChoreCompletion.objects.create(
                chore=chore, user=child, completed_date=date(2026, 10, 18), status="approved",
                decided_at=FIXED_NOW - timedelta(hours=2), decided_by=parent,
                reward_amount_snapshot="0.00", coin_reward_snapshot=0,
            )
            goal = ChallengeGoal.objects.create(
                id=801, user=child, family=household.family, created_by=parent,
                name="Read together", metric="minutes", target="20", unit="minutes",
                timezone_name="America/Phoenix", starts_at=FIXED_NOW - timedelta(days=1),
                ends_at=FIXED_NOW + timedelta(days=1),
            )
            ChallengeOccurrence.objects.create(
                id=802, goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
                progress="7.500", snapshot={"name": "Read together", "target": "20.000", "unit": "minutes"},
            )
            badge = Badge.objects.create(id=901, name="Steady learner", criteria_type="homework_count")
            UserBadge.objects.create(user=child, badge=badge)
            project = Project.objects.create(
                id=401, title="Weekend build", assigned_to=child, created_by=parent, status="in_progress",
            )
            TimeEntry.objects.create(
                user=child, project=project, status="completed",
                clock_in=FIXED_NOW - timedelta(minutes=90), clock_out=FIXED_NOW,
            )
            outsider = make_family("Other Overview Fixture", children=[{"username": "other-child"}])
            HomeworkAssignment.objects.create(
                title="Other family's homework", subject="math", assigned_to=outsider.children[0],
                created_by=parent, due_date=date(2026, 10, 18),
            )
            self.client.force_authenticate(parent)
            body = self.assert_response_fixture(self.client.get("/api/dashboard/"), "parent-family-overview.json")
            self.assertEqual(body["family_overview"]["date"], "2026-10-18")
            self.assertEqual([row["kid_id"] for row in body["family_overview"]["children"]], [7, 8])
            self.assertNotIn("private", str(body["family_overview"]))


class ParentDeliveryApiFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def test_real_world_approval_and_delivery_keep_distinct_audit_receipts(self):
        from apps.rewards.models import Reward, RewardRedemption
        from apps.rewards.services import CoinService
        from apps.rewards.models import CoinLedger
        household = make_family(
            "Parent Delivery Fixture", family_id=62,
            parents=[{"id": 6, "username": "delivery-parent"}],
            children=[{"id": 7, "username": "delivery-child", "display_name": "Abby"}],
        )
        parent, child = household.parents[0], household.children[0]
        self.client.force_authenticate(user=parent)
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            reward = Reward.objects.create(id=901, family=household.family, name="Park afternoon", cost_coins=20)
            CoinService.award_coins(child, 50, CoinLedger.Reason.ADJUSTMENT)
            # Fixed synthetic request identity, including its frozen promise.
            redemption = RewardRedemption.objects.create(id=902, user=child, reward=reward, coin_cost_snapshot=20)
            approved = self.client.post(f"/api/redemptions/{redemption.pk}/approve/", {"notes": "Saturday after lunch"}, format="json")
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["status"], "approved")
            self.assert_response_fixture(approved, "parent-reward-approved.json")
            from apps.projects.parent_attention import parent_attention
            signal = parent_attention(parent)
            self.assertEqual(signal["counts"]["deliveries"], 1)
            delivered = self.client.post(f"/api/redemptions/{redemption.pk}/deliver/", {}, format="json")
            self.assertEqual(delivered.status_code, 200)
            self.assertEqual(delivered.json()["status"], "fulfilled")
            self.assert_response_fixture(delivered, "parent-reward-delivered.json")
            self.assertEqual(delivered.json()["decided_at"], approved.json()["decided_at"])
            self.assertEqual(parent_attention(parent)["counts"]["deliveries"], 0)
