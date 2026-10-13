"""Distance is factual progress, independent of the activity reward allowance."""
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIClient

from config.tests.factories import make_family
from apps.movement.models import MovementSession, MovementType


class MovementDistanceTests(TestCase):
    def setUp(self):
        family = make_family("runners", parents=[{"username": "parent"}], children=[{"username": "runner"}])
        self.child = family.children[0]
        self.running = MovementType.objects.create(name="Running", slug="running")
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def payload(self, **overrides):
        return {"movement_type_id": self.running.pk, "duration_minutes": 20,
                "distance": "0.75", "distance_unit": "mi", **overrides}

    def test_fractional_miles_are_saved_as_exact_metres(self):
        response = self.client.post("/api/movement-sessions/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["distance_meters"], "1207.008")
        self.assertEqual(response.data["distance"], "0.75")

    def test_kilometres_are_normalized_and_missing_distance_remains_unknown(self):
        response = self.client.post("/api/movement-sessions/", self.payload(distance="1.25", distance_unit="km"), format="json")
        self.assertEqual(response.data["distance_meters"], "1250.000")
        response = self.client.post("/api/movement-sessions/", {
            "movement_type_id": self.running.pk, "duration_minutes": 20,
        }, format="json")
        self.assertIsNone(response.data["distance_meters"])

    def test_retrying_saved_request_cannot_add_a_second_session(self):
        payload = self.payload(client_request_id=str(uuid4()))
        first = self.client.post("/api/movement-sessions/", payload, format="json")
        second = self.client.post("/api/movement-sessions/", payload, format="json")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 1)

    def test_request_key_cannot_be_reused_for_different_distance(self):
        payload = self.payload(client_request_id=str(uuid4()))
        self.client.post("/api/movement-sessions/", payload, format="json")
        response = self.client.post("/api/movement-sessions/", {**payload, "distance": "2"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_distance_writes_nothing(self):
        for value in ("0", "-1", "NaN", "Infinity", "1.0001"):
            with self.subTest(value=value):
                response = self.client.post("/api/movement-sessions/", self.payload(distance=value), format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(MovementSession.objects.count(), 0)
