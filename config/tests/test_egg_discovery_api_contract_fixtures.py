"""Synthetic discovery envelopes rendered by authenticated Django endpoints."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import UUID

from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.egg_discoveries.models import (
    DiscoveryActivityCredit, DiscoveryRequest, DiscoverySearch, EggDiscovery, PracticeSession,
)
from apps.egg_discoveries.tests.factories import ASSET_POLICY, make_catalog
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


FIXED_NOW = datetime(2026, 10, 20, 19, tzinfo=datetime_timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={},
    RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY,
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class EggDiscoveryApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        self.clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        household = make_family(
            "Discovery Fixture Family", family_id=81,
            parents=[{"id": 81, "username": "discovery-fixture-parent"}],
            children=[{"id": 82, "username": "discovery-fixture-child"}],
        )
        household.family.timezone = "America/Phoenix"
        household.family.save(update_fields=["timezone"])
        self.child = household.children[0]
        # Previous PostgreSQL tests advance sequences even after their rows
        # roll back. Reset only these synthetic fixture models before seeding.
        models = [PetSpecies, PotionType, ItemDefinition, EggDiscovery, DiscoverySearch,
                  DiscoveryRequest, DiscoveryActivityCredit, PracticeSession]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
        self.catalog = make_catalog()
        self.client.force_authenticate(self.child)
        self.next_request = 1

    def _uuid(self):
        value = str(UUID(int=self.next_request))
        self.next_request += 1
        return value

    def _select(self, key):
        response = self.client.post("/api/egg-discoveries/select/", {
            "offer_key": key, "client_request_id": self._uuid(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def _practice(self, minutes=30):
        response = self.client.post("/api/egg-discoveries/practice/", {
            "name": "Drawing practice", "minutes": minutes, "client_request_id": self._uuid(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def _read(self, minutes=30):
        book = self.client.post("/api/reading-books/", {
            "title": "Synthetic discovery reading", "client_request_id": self._uuid(),
        }, format="json")
        self.assertEqual(book.status_code, 201, book.content)
        response = self.client.post("/api/reading-sessions/", {
            "book": book.json()["id"], "duration_minutes": minutes,
            "client_request_id": self._uuid(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_catalog_disabled_ordinary_progress_and_pause(self):
        catalog = self.assert_response_fixture(self.client.get(
            "/api/egg-discoveries/"), "egg-discovery-catalog.json")
        self.assertFalse(next(offer for offer in catalog["offers"] if offer["tier"] == "rare")["eligible"])
        self.assertFalse(EggDiscovery.objects.exists())
        self._select(self.catalog.ordinary.key)
        active = self.assert_response_fixture(self._practice(90), "egg-discovery-ordinary-active.json", status=201)
        discovery = EggDiscovery.objects.get(user=self.child)
        self.assertEqual(discovery.minutes["practice"], 90)
        self.assertEqual(active["active_id"], discovery.pk)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        paused = self.assert_response_fixture(self.client.post(
            f"/api/egg-discoveries/{discovery.pk}/pause/", {"client_request_id": self._uuid()}, format="json",
        ), "egg-discovery-paused.json")
        self.assertIsNone(paused["active_id"])
        self.assertEqual(paused["discoveries"][0]["minutes"]["practice"], 90)
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            self.assert_response_fixture(self.client.get(
                "/api/egg-discoveries/"), "egg-discovery-disabled.json")

    def test_rare_misses_then_fifth_search_delivers_exact_saved_reward_once(self):
        for pair in (self.catalog.ordinary, self.catalog.other):
            UserPet.objects.create(user=self.child, species=pair.species, potion=self.catalog.base)
        self._select(self.catalog.rare.key)
        # Replace this service's module reference so reading's existing game
        # loop retains its separate random-drop behavior.
        with patch("apps.egg_discoveries.services.random") as random_source:
            random_source.random.return_value = 0.9
            for search in range(1, 6):
                self._read()
                response = self._practice()
                if search == 1:
                    missed = self.assert_response_fixture(response, "egg-discovery-rare-missed.json", status=201)
                    self.assertFalse(missed["discoveries"][0]["searches"][0]["found"])
                if search == 5:
                    complete = self.assert_response_fixture(response, "egg-discovery-rare-guaranteed.json", status=201)
            self.assertEqual(random_source.random.call_count, 4)
        saved = EggDiscovery.objects.get(user=self.child)
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.searches.count(), 5)
        self.assertTrue(saved.searches.get(number=5).guaranteed)
        self.assertEqual(complete["discoveries"][0]["receipt"], saved.reward_receipt)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.rare.egg).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.potion).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.food).quantity, 2)
        self.assertEqual(self.client.get("/api/egg-discoveries/").json(), complete)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.catalog.rare.egg).quantity, 1)

    def test_accepted_seasonal_start_window_does_not_become_a_finish_deadline(self):
        seasons = {self.catalog.ordinary.key: {"starts_on": "2026-10-01", "ends_on": "2026-10-31"}}
        with override_settings(EGG_DISCOVERY_SEASONS=seasons):
            self._select(self.catalog.ordinary.key)
            with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(days=15)):
                self._practice(45)
                retained = self.assert_response_fixture(self.client.get(
                    "/api/egg-discoveries/"), "egg-discovery-season-retained.json")
                self.assertEqual(retained["discoveries"][0]["status"], "active")
                self.assertEqual(retained["discoveries"][0]["minutes"]["practice"], 45)
                self.assertEqual(retained["discoveries"][0]["season"]["ends_on"], "2026-10-31")
