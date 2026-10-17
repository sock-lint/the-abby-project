"""The designer workbench uses anonymous simulations, never household records."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class ProgressionLabApiTests(APITestCase):
    metadata_url = "/api/rpg/progression-lab/"
    simulation_url = "/api/rpg/progression-lab/simulate/"

    def setUp(self):
        cache.clear()
        family = make_family(
            "Simulation permissions",
            parents=[
                {"username": "designer", "is_staff": True},
                {"username": "parent"},
            ],
            children=[{"username": "child", "is_staff": True}],
        )
        self.designer, self.parent = family.parents
        self.child = family.children[0]

    def test_anonymous_requests_cannot_read_rules_or_run_simulations(self):
        self.assertEqual(self.client.get(self.metadata_url).status_code, 401)
        self.assertEqual(self.client.post(self.simulation_url, {}, format="json").status_code, 401)

    def test_regular_parent_and_staff_child_cannot_use_designer_tools(self):
        for user in (self.parent, self.child):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(self.metadata_url).status_code, 403)
                self.assertEqual(self.client.post(self.simulation_url, {}, format="json").status_code, 403)

    def test_rejects_real_user_targeting_and_unknown_assumptions(self):
        self.client.force_authenticate(self.designer)
        for payload in ({"user_id": self.child.pk}, {"initial_coins": 1000}, {"trials": 41}):
            with self.subTest(payload=payload):
                response = self.client.post(self.simulation_url, payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.metadata_url, {"user_id": self.child.pk}).status_code, 400)

    def test_metadata_is_runtime_rules_and_has_an_explicit_zero_state(self):
        self.client.force_authenticate(self.designer)
        response = self.client.get(self.metadata_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        metadata = response.json()
        self.assertEqual(metadata["defaults"]["horizon_days"], 90)
        self.assertEqual(metadata["limits"]["trials"]["max"], 40)
        self.assertEqual(metadata["coverage"]["initial_state"], {
            "coins": 0, "xp": 0, "pets": 0, "mounts": 0, "inventory": 0,
        })
        self.assertEqual(len(metadata["rules_fingerprint"]), 64)
        self.assertNotIn("user_id", metadata)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_shared_browser_cache_and_retry_markers_do_not_select_accounts(self):
        self.client.force_authenticate(self.designer)
        plain = self.client.get(self.metadata_url)
        browser = self.client.get(self.metadata_url, {"_abby_session": "synthetic-session", "_abby_retry": "1"})
        self.assertEqual(browser.status_code, 200)
        self.assertEqual(browser.json(), plain.json())
        rejected = self.client.get(self.metadata_url, {
            "_abby_session": "synthetic-session", "user_id": self.child.pk,
        })
        self.assertEqual(rejected.status_code, 400)

    def test_anonymous_scenario_returns_reproducible_json_without_creating_accounts(self):
        from apps.accounts.models import User
        from apps.rewards.models import CoinLedger
        from apps.rpg.models import UserInventory

        self.client.force_authenticate(self.designer)
        before = (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count())
        config = {"horizon_days": 30, "trials": 1, "seed": 123}
        first = self.client.post(self.simulation_url, config, format="json")
        second = self.client.post(self.simulation_url, config, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(first.json()["trace"]), 30)
        self.assertEqual(first.json()["config"]["seed"], 123)
        self.assertEqual(before, (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count()))

    def test_rejects_wrong_wire_types_and_query_targeting(self):
        self.client.force_authenticate(self.designer)
        for payload in ({"trials": True}, {"seed": "42"}, {"journal_per_day": 1}, [], [1], {"horizon_days": 10000}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.simulation_url, payload, format="json").status_code, 400)
        response = self.client.post(self.simulation_url + "?user_id=1", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_repeated_expensive_requests_are_throttled_before_running_the_engine(self):
        self.client.force_authenticate(self.designer)
        with patch("apps.rpg.progression_views.simulate_progression", return_value={"schema_version": 1}) as engine:
            for _ in range(10):
                self.assertEqual(self.client.post(self.simulation_url, {}, format="json").status_code, 200)
            response = self.client.post(self.simulation_url, {}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(engine.call_count, 10)

    def test_catalog_bounds_return_a_recoverable_service_error(self):
        self.client.force_authenticate(self.designer)
        with patch("apps.rpg.progression_views.describe_progression", side_effect=ValueError("Global catalog exceeds its limit.")):
            metadata = self.client.get(self.metadata_url)
        with patch("apps.rpg.progression_views.simulate_progression", side_effect=ValueError("Global catalog exceeds its limit.")):
            report = self.client.post(self.simulation_url, {}, format="json")
        for response in (metadata, report):
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail": "Global catalog exceeds its limit."})
