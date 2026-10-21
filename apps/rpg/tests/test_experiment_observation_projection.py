"""Notebook projections must not load household checkpoints for author-only clients."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.rpg.models import ProgressionExperiment, ProgressionObservation
from apps.rpg.progression.experiments import get_experiment
from config.tests.factories import make_family


class ExperimentObservationProjectionTests(TestCase):
    def test_redacted_detail_omits_household_payload_and_its_database_read(self):
        family = make_family("Experiment projection", parents=[{"username": "projection-parent", "is_staff": True}])
        actor = family.parents[0]
        experiment = ProgressionExperiment.objects.create(
            actor=actor, family=family.family, name="Private design", hypothesis="Synthetic hypothesis",
        )
        observation = ProgressionObservation.objects.create(
            experiment=experiment, experiment_revision=1,
            payload={"status": "available", "private_household_marker": "synthetic-private-evidence"}, binding={},
        )
        with CaptureQueriesContext(connection) as queries:
            redacted = get_experiment(actor, experiment.pk, include_observations=False)
        self.assertEqual(redacted["observations"], [])
        self.assertNotIn("synthetic-private-evidence", str(redacted))
        self.assertFalse(any("rpg_progressionobservation" in query["sql"].lower() for query in queries))
        native = get_experiment(actor, experiment.pk)
        self.assertEqual(native["observations"][0]["id"], str(observation.pk))
        self.assertEqual(native["observations"][0]["payload"], observation.payload)
