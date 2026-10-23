"""Content-free usage reports produced by the real authenticated endpoint."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.chores.models import Chore
from apps.usage.models import UsageCollectionState, UsageEvent, UsageVisit
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared_fixtures


NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class UsageApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        self.clock = patch("django.utils.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.household = make_family(
            "Synthetic usage household", family_id=81,
            parents=[{"id": 21, "username": "usage-parent", "is_staff": True}],
            children=[{"id": 22, "username": "usage-child"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]

    def test_real_submissions_approval_and_foreground_visits_produce_aggregate_reports(self):
        UsageCollectionState.objects.create(pk=1, started_at=NOW - timedelta(days=70))
        type(self.household.family).objects.filter(pk=self.household.family.pk).update(created_at=NOW - timedelta(days=50))
        type(self.parent).objects.filter(family=self.household.family).update(date_joined=NOW - timedelta(days=50))
        chore = Chore.objects.create(
            id=891, family=self.household.family, created_by=self.parent,
            assigned_to=self.child, title="Synthetic private task title",
            reward_amount="0.00", coin_reward=0, xp_reward=0,
        )
        submissions = []
        for age in (35, 16, 8, 2):
            with patch("django.utils.timezone.now", return_value=NOW - timedelta(days=age)):
                self.client.force_authenticate(self.child)
                response = self.client.post(
                    f"/api/chores/{chore.pk}/complete/",
                    {"notes": "Synthetic private submission content"}, format="json",
                )
                self.assertEqual(response.status_code, 201, response.data)
                submissions.append(response.data["id"])
                self.assertEqual(self.client.post("/api/usage/visit/", {}, format="json").status_code, 204)
        self.client.force_authenticate(self.parent)
        with patch("django.utils.timezone.now", return_value=NOW - timedelta(days=7)):
            decision = self.client.post(f"/api/chore-completions/{submissions[2]}/approve/", {}, format="json")
            self.assertEqual(decision.status_code, 200, decision.data)
        self.assertEqual(self.client.post("/api/usage/visit/", {}, format="json").status_code, 204)

        foreign = make_family(
            "Other synthetic household", family_id=82,
            parents=[{"id": 23, "username": "other-usage-parent", "is_staff": True}],
            children=[{"id": 24, "username": "other-usage-child"}],
        )
        other_chore = Chore.objects.create(
            family=foreign.family, created_by=foreign.parents[0], assigned_to=foreign.children[0],
            title="Other family's private task", reward_amount="0.00", coin_reward=0, xp_reward=0,
        )
        self.client.force_authenticate(foreign.children[0])
        self.assertEqual(self.client.post(f"/api/chores/{other_chore.pk}/complete/", {}, format="json").status_code, 201)
        self.client.force_authenticate(self.parent)
        before = (UsageEvent.objects.count(), UsageVisit.objects.count())
        body = self.assert_response_fixture(self.client.get("/api/admin/usage/"), "usage-family-observed.json")
        self.assertEqual(body["summary"]["current"]["active_families"], 1)
        self.assertEqual(body["summary"]["current"]["active_children"], 1)
        self.assertEqual(body["summary"]["current"]["active_parents"], 1)
        self.assertEqual(body["summary"]["current"]["completed_activities"], 3)
        self.assertEqual(body["summary"]["previous"]["completed_activities"], 1)
        self.assertEqual(body["retention"]["week_1"]["returned_families"], 1)
        self.assertEqual(body["retention"]["week_4"]["returned_families"], 1)
        self.assertEqual(body["friction"]["pending_reviews"], 3)
        self.assertEqual(before, (UsageEvent.objects.count(), UsageVisit.objects.count()))
        self.assertNotIn("Synthetic private", str(body))
        self.assertNotIn("usage-child", str(body))

        filtered = self.assert_response_fixture(
            self.client.get("/api/admin/usage/", {"days": 7, "role": "child", "feature": "chores"}),
            "usage-family-child-chores.json",
        )
        self.assertEqual(filtered["summary"]["current"]["completed_activities"], 1)
        self.assertEqual(filtered["summary"]["current"]["active_parents"], 0)
        self.assertEqual([row["feature"] for row in filtered["features"]], ["chores"])

        self.parent.is_superuser = True
        self.parent.save(update_fields=["is_superuser"])
        deployment = self.assert_response_fixture(
            self.client.get("/api/admin/usage/", {"scope": "deployment"}), "usage-deployment-observed.json",
        )
        self.assertEqual(deployment["summary"]["current"]["active_families"], 2)
        self.assertTrue(deployment["can_view_deployment"])

    def test_empty_report_preserves_unobserved_history_and_no_mature_cohort(self):
        self.client.force_authenticate(self.parent)
        body = self.assert_response_fixture(self.client.get("/api/admin/usage/"), "usage-family-empty.json")
        self.assertIsNone(body["collection"]["started_at"])
        self.assertFalse(body["collection"]["history_complete"])
        self.assertIsNone(body["retention"]["week_1"]["rate"])
        self.assertEqual(body["summary"]["current"]["actions"], 0)
        self.assertFalse(UsageCollectionState.objects.exists())
