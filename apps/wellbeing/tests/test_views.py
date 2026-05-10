"""HTTP-layer smoke for the wellbeing endpoints.

Service-level behaviour (validation, idempotency, deterministic roll, coin
trickle gating) is pinned in test_services.py. This file covers the thin
DRF wrapper: status codes, body shape, self-scoping, error mapping.
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.wellbeing.services import _load_affirmations


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class WellbeingTodayViewTests(TestCase):
    def setUp(self):
        _load_affirmations.cache_clear()
        self.user = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_get_today_creates_row_and_returns_payload_shape(self):
        response = self.client.get("/api/wellbeing/today/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Stable shape — frontend WellbeingCard reads these keys directly.
        self.assertIn("affirmation", body)
        self.assertIn("text", body["affirmation"])
        self.assertGreater(len(body["affirmation"]["text"]), 0)
        self.assertEqual(body["gratitude_lines"], [])
        self.assertFalse(body["gratitude_paid"])
        self.assertEqual(body["max_lines"], 3)

    def test_get_today_is_idempotent_across_requests(self):
        first = self.client.get("/api/wellbeing/today/").json()
        second = self.client.get("/api/wellbeing/today/").json()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["affirmation"]["slug"], second["affirmation"]["slug"])

    def test_post_gratitude_round_trip_returns_paid_flag_and_coin_amount(self):
        response = self.client.post(
            "/api/wellbeing/today/gratitude/",
            {"lines": ["one", "two"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["gratitude_lines"], ["one", "two"])
        self.assertTrue(body["gratitude_paid"])
        self.assertTrue(body["freshly_paid"])
        self.assertGreater(body["coin_awarded"], 0)

    def test_post_gratitude_validation_returns_400_with_error_string(self):
        response = self.client.post(
            "/api/wellbeing/today/gratitude/",
            {"lines": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_anonymous_request_is_rejected(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/wellbeing/today/").status_code, 401)
        self.assertEqual(
            anon.post("/api/wellbeing/today/gratitude/", {"lines": ["x"]}, format="json").status_code,
            401,
        )

    def test_user_id_in_post_body_is_ignored_self_scoped(self):
        """Any user_id field on the request body must NOT redirect the write
        away from request.user. The view binds writes to the requester."""
        other = User.objects.create_user(
            username="rival", password="pw", role="child",
        )
        response = self.client.post(
            "/api/wellbeing/today/gratitude/",
            {"lines": ["mine"], "user_id": other.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        # The other user has no row — the write landed on request.user.
        from apps.wellbeing.models import DailyWellbeingEntry
        self.assertFalse(DailyWellbeingEntry.objects.filter(user=other).exists())
        self.assertTrue(DailyWellbeingEntry.objects.filter(user=self.user).exists())
