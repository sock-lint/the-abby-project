"""Lifecycle scope checks never deserialize retained anonymous Lab reports."""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import JSONField
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.rpg.models import ProgressionComparison, ProgressionDecision, ProgressionExperiment, ProgressionObservation
from config.tests.factories import make_family


PROTECTED_MODELS = (ProgressionComparison, ProgressionExperiment, ProgressionObservation)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionEvidenceDeletionTests(TestCase):
    def setUp(self):
        household = make_family("Lab deletion", parents=[
            {"username": "lab-owner", "is_staff": True}, {"username": "lab-successor"},
        ], children=[{"username": "lab-child"}])
        self.family = household.family
        self.parent, self.successor = household.parents
        self.other = make_family("Other Lab", parents=[{"username": "other-lab-owner"}])
        self.client = APIClient()
        self.authenticate(self.parent)
        self.experiment = self.evidence(self.parent)

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def evidence(self, actor):
        payload = {"synthetic_large_field": "bounded-probe-" * 100}
        experiment = ProgressionExperiment.objects.create(
            actor=actor, family=actor.family, name="Synthetic experiment", hypothesis="Synthetic hypothesis",
            config=payload, targets=[payload],
        )
        comparison = ProgressionComparison.objects.create(
            experiment=experiment, experiment_revision=1, inputs=payload, control=payload,
            candidate=payload, evaluation=payload, binding=payload,
        )
        ProgressionDecision.objects.create(
            experiment=experiment, comparison=comparison, outcome="keep_testing",
            rationale="Retest", next_action="Review again", review_on=date(2026, 10, 25),
        )
        ProgressionObservation.objects.create(experiment=experiment, experiment_revision=1, payload=payload, binding=payload)
        return experiment

    def assert_lightweight(self, action, expected_status):
        decoded = []
        original = JSONField.from_db_value

        def observe(field, value, expression, connection):
            if field.model in PROTECTED_MODELS:
                decoded.append((field.model._meta.label_lower, field.name))
            return original(field, value, expression, connection)

        with patch.object(JSONField, "from_db_value", observe), CaptureQueriesContext(connection) as queries:
            response = action()
        self.assertEqual(response.status_code, expected_status, response.data)
        self.assertEqual(decoded, [], "Lifecycle fetched Lab JSON that is irrelevant to family authorization")
        for query in queries:
            sql = query["sql"]
            if not sql.lstrip().upper().startswith("SELECT"):
                continue
            selected = sql.split(" FROM ", 1)[0]
            for model in PROTECTED_MODELS:
                for field in model._meta.concrete_fields:
                    if isinstance(field, JSONField):
                        column = f'{connection.ops.quote_name(model._meta.db_table)}.{connection.ops.quote_name(field.column)}'
                        self.assertNotIn(column, selected)
        return response

    def delete_self(self):
        return self.client.post("/api/account/lifecycle/delete/", {
            "password": "pw", "confirm_username": self.parent.username, "successor_id": self.successor.pk,
        }, format="json")

    def test_self_departure_deletes_reports_without_loading_payload_columns(self):
        foreign = self.evidence(self.other.parents[0])
        self.assert_lightweight(self.delete_self, 204)
        self.assertFalse(ProgressionExperiment.objects.filter(pk=self.experiment.pk).exists())
        self.assertFalse(ProgressionComparison.objects.filter(experiment_id=self.experiment.pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk=self.parent.pk).exists())
        self.assertTrue(ProgressionExperiment.objects.filter(pk=foreign.pk).exists())

    def test_family_closure_deletes_the_evidence_without_loading_payload_columns(self):
        self.successor.is_active = False
        self.successor.save(update_fields=["is_active"])
        preview = self.client.get("/api/account/lifecycle/").data
        self.assert_lightweight(lambda: self.client.post("/api/account/lifecycle/close-family/", {
            "password": "pw", "confirm_family_slug": self.family.slug, "family_version": preview["family_version"],
        }, format="json"), 204)
        self.assertFalse(ProgressionExperiment.objects.exists())
        self.assertFalse(ProgressionComparison.objects.exists())
        self.assertFalse(ProgressionDecision.objects.exists())
        self.assertFalse(ProgressionObservation.objects.exists())

    def test_parent_managed_departure_keeps_the_scope_check_lightweight(self):
        self.authenticate(self.successor)
        self.assert_lightweight(lambda: self.client.delete(f"/api/parents/{self.parent.pk}/"), 204)
        self.assertFalse(ProgressionExperiment.objects.filter(pk=self.experiment.pk).exists())

    def test_foreign_comparison_parent_is_still_checked_without_decoding_its_report(self):
        foreign = self.evidence(self.other.parents[0])
        comparison = ProgressionComparison.objects.only("pk").get(experiment=foreign)
        ProgressionDecision.objects.filter(experiment=self.experiment).update(comparison=comparison)
        response = self.assert_lightweight(self.delete_self, 409)
        self.assertNotIn("bounded-probe", str(response.data))
        self.assertTrue(ProgressionExperiment.objects.filter(pk=self.experiment.pk).exists())
        self.assertTrue(ProgressionExperiment.objects.filter(pk=foreign.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.parent.pk).exists())
