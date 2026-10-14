"""Distance is factual progress, independent of the activity reward allowance."""
from decimal import Decimal
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

    def distance_goal(self, target, unit="mi", **overrides):
        from apps.quests.models import ChallengeOccurrence
        parent_client = APIClient()
        parent_client.force_authenticate(self.child.family.primary_parent)
        response = parent_client.post("/api/challenges/goals/", {
            "user_id": self.child.pk, "name": f"Run {target} {unit}", "trigger_type": "movement_session",
            "movement_type_id": self.running.pk, "metric": "distance", "target": target, "unit": unit,
            "period": "this_week", "coin_reward": 7, "xp_reward": 0, **overrides,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return ChallengeOccurrence.objects.get(pk=response.data["id"].split(":")[1])

    def test_fractional_miles_are_saved_as_exact_metres(self):
        response = self.client.post("/api/movement-sessions/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["distance_meters"], "1207.008")
        self.assertEqual(response.data["distance"], "0.75")

    def test_ordinary_miles_roundtrip_through_post_read_list_and_uuid_retry(self):
        for distance, metres in (("3.1", "4988.966"), ("1.1", "1770.278"), ("0.333", "535.912")):
            payload = self.payload(distance=distance, client_request_id=str(uuid4()))
            first = self.client.post("/api/movement-sessions/", payload, format="json")
            self.assertEqual(first.status_code, 201, first.data)
            detail = self.client.get(f"/api/movement-sessions/{first.data['id']}/")
            self.assertEqual(detail.status_code, 200, detail.data)
            listing = self.client.get("/api/movement-sessions/")
            listed = next(row for row in listing.data["results"] if row["id"] == first.data["id"])
            retry = self.client.post("/api/movement-sessions/", payload, format="json")
            self.assertEqual(retry.status_code, 201, retry.data)
            for surface, body in (("POST", first.data), ("GET", detail.data), ("list", listed), ("retry", retry.data)):
                with self.subTest(distance=distance, surface=surface):
                    self.assertEqual(body["distance"], distance)
                    self.assertIsInstance(body["distance"], str)
                    self.assertEqual(body["id"], first.data["id"])
                    self.assertEqual(body["distance_meters"], metres)
            self.assertEqual(MovementSession.objects.filter(user=self.child, client_request_id=payload["client_request_id"]).count(), 1)

    def test_display_precision_and_boundaries_are_stable_for_both_units(self):
        for unit in ("mi", "km"):
            for supplied, expected in (("3.100", "3.1"), ("1.1", "1.1"), (".333", "0.333"),
                                       ("0.001", "0.001"), ("1000.000", "1000")):
                with self.subTest(unit=unit, distance=supplied):
                    payload = self.payload(distance=supplied, distance_unit=unit, client_request_id=str(uuid4()))
                    response = self.client.post("/api/movement-sessions/", payload, format="json")
                    self.assertEqual(response.status_code, 201, response.data)
                    detail = self.client.get(f"/api/movement-sessions/{response.data['id']}/")
                    listing = self.client.get("/api/movement-sessions/")
                    listed = next(row for row in listing.data["results"] if row["id"] == response.data["id"])
                    retry = self.client.post("/api/movement-sessions/", payload, format="json")
                    self.assertEqual(retry.status_code, 201, retry.data)
                    for body in (response.data, detail.data, listed, retry.data):
                        self.assertEqual((body["distance"], body["distance_unit"]), (expected, unit))
                        self.assertIsInstance(body["distance"], str)
                    self.assertEqual(MovementSession.objects.filter(user=self.child, client_request_id=payload["client_request_id"]).count(), 1)

    def test_display_rounding_preserves_saved_metres_goal_progress_and_uuid_retry(self):
        from apps.quests.models import ChallengeContribution, ChallengeOccurrence
        parent_client = APIClient()
        parent_client.force_authenticate(self.child.family.primary_parent)
        goal = parent_client.post("/api/challenges/goals/", {
            "user_id": self.child.pk, "name": "Run 3.1 miles", "trigger_type": "movement_session",
            "movement_type_id": self.running.pk, "metric": "distance", "target": "3.1", "unit": "mi",
            "period": "this_week", "coin_reward": 0, "xp_reward": 0,
        }, format="json")
        self.assertEqual(goal.status_code, 201, goal.data)
        payload = self.payload(distance="3.1", client_request_id=str(uuid4()))
        first = self.client.post("/api/movement-sessions/", payload, format="json")
        retry = self.client.post("/api/movement-sessions/", payload, format="json")
        self.assertEqual((first.status_code, retry.status_code), (201, 201))
        self.assertEqual((first.data["distance"], retry.data["distance"]), ("3.1", "3.1"))
        self.assertEqual(MovementSession.objects.get(user=self.child).distance_meters, Decimal("4988.966"))
        occurrence = ChallengeOccurrence.objects.get(pk=goal.data["id"].split(":")[1])
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("3.1"), "completed"))
        self.assertEqual(ChallengeContribution.objects.filter(occurrence=occurrence).count(), 1)

    def test_fractional_contributions_complete_the_exact_sum_once(self):
        occurrence = self.distance_goal("0.3")
        for distance in ("0.1", "0.2"):
            payload = self.payload(distance=distance, client_request_id=str(uuid4()))
            first = self.client.post("/api/movement-sessions/", payload, format="json")
            retry = self.client.post("/api/movement-sessions/", payload, format="json")
            self.assertEqual((first.status_code, retry.status_code), (201, 201))
            self.assertEqual(first.data["id"], retry.data["id"])
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("0.300"), "completed"))
        self.assertEqual(list(occurrence.contributions.order_by("pk").values_list("amount", flat=True)),
                         [Decimal("0.100"), Decimal("0.200")])
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 2)

    def test_rounded_miles_complete_the_exact_cumulative_target(self):
        occurrence = self.distance_goal("3.1")
        for distance in ("1.1", "2"):
            payload = self.payload(distance=distance, client_request_id=str(uuid4()))
            first = self.client.post("/api/movement-sessions/", payload, format="json")
            retry = self.client.post("/api/movement-sessions/", payload, format="json")
            self.assertEqual((first.status_code, retry.status_code), (201, 201))
            self.assertEqual(first.data["id"], retry.data["id"])
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("3.100"), "completed"))
        self.assertEqual(list(occurrence.contributions.order_by("pk").values_list("amount", flat=True)),
                         [Decimal("1.100"), Decimal("2.000")])
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 2)

    def test_mixed_units_round_half_up_at_the_saved_goal_precision(self):
        # 1.509 mi is saved as 2428.500 m. A km goal receives 2.429,
        # matching PostgreSQL numeric rounding rather than half-even 2.428.
        occurrence = self.distance_goal("2.429", unit="km")
        response = self.client.post("/api/movement-sessions/", self.payload(distance="1.509"), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["distance"], response.data["distance_meters"]), ("1.509", "2428.500"))
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("2.429"), "completed"))
        self.assertEqual(occurrence.contributions.get().amount, Decimal("2.429"))
        self.assertEqual(occurrence.reward_receipt["coins"], 7)

    def test_same_week_backfill_uses_canonical_distance_before_completion(self):
        payload = self.payload(distance="3.1", client_request_id=str(uuid4()))
        response = self.client.post("/api/movement-sessions/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        occurrence = self.distance_goal("3.1")
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("3.100"), "completed"))
        self.assertEqual(occurrence.contributions.get().amount, Decimal("3.100"))
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        retry = self.client.post("/api/movement-sessions/", payload, format="json")
        self.assertEqual(retry.data["id"], response.data["id"])
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.contributions.count(), 1)
        self.assertEqual(occurrence.reward_receipt["coins"], 7)

    def test_deleting_unpaid_distance_recalculates_without_paying_or_retry_credit(self):
        occurrence = self.distance_goal("1")
        sessions = []
        for distance in ("0.1", "0.2"):
            payload = self.payload(distance=distance, client_request_id=str(uuid4()))
            response = self.client.post("/api/movement-sessions/", payload, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            sessions.append((response.data["id"], payload))
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, Decimal("0.300"))
        removed = self.client.delete(f"/api/movement-sessions/{sessions[0][0]}/")
        self.assertEqual(removed.status_code, 204, removed.data)
        retry = self.client.post("/api/movement-sessions/", sessions[1][1], format="json")
        self.assertEqual(retry.data["id"], sessions[1][0])
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (Decimal("0.200"), "active"))
        self.assertIsNone(occurrence.awarded_at)
        self.assertEqual(occurrence.reward_receipt, {})
        self.assertEqual(occurrence.contributions.filter(activity__voided=False).count(), 1)

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
