"""Actual archive/list receipts with fixed synthetic private authoring identities."""
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.rpg.models import ProgressionExperiment, RPGContentDraft, RPGEditorialDraft
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"], PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringArchiveResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    @patch("django.utils.timezone.now", return_value=datetime(2026, 10, 22, 12, tzinfo=timezone.utc))
    def test_archive_history_restore_and_original_operation_replay_are_real_wire_bodies(self, _now):
        actor = make_family("Synthetic archive studio", family_id=64,
            parents=[{"id": 91, "username": "fixture-archive-designer", "is_staff": True}]).parents[0]
        self.client.force_authenticate(actor)
        roots = {"content": "/api/rpg/content-workbench/drafts/", "editorial": "/api/rpg/editorial/drafts/",
                 "experiment": "/api/rpg/progression-lab/experiments/"}
        models = {"content": RPGContentDraft, "editorial": RPGEditorialDraft, "experiment": ProgressionExperiment}
        for index, kind in enumerate(roots, start=1):
            values = {"actor": actor, "family": actor.family, "name": "Retained synthetic work"}
            if kind == "editorial":
                values["section"] = "affirmations"
            if kind == "experiment":
                values.update(hypothesis="A retained anonymous hypothesis.", config={"horizon_days": 30, "trials": 1})
            object_id = UUID(f"00000000-0000-4000-8000-{index:012d}")
            models[kind].objects.create(id=object_id, **values)
            url = f"{roots[kind]}{object_id}/archive/"
            data = {"revision": 1, "is_archived": True, "request_id": f"10000000-0000-4000-8000-{index:012d}", "confirmation": True}
            result = self.assert_response_fixture(self.client.post(url, data, format="json"), f"authoring-{kind}-archived.json")
            self.assertEqual(result["operation"], {"is_archived": True, "revision": 2})
            default = self.client.get(roots[kind])
            self.assertEqual(default.status_code, 200)
            self.assertEqual(default.json()["total"], 0)
            history = self.assert_response_fixture(self.client.get(roots[kind], {"include_archived": "true", "limit": 1}),
                f"authoring-{kind}-history.json")
            self.assertEqual(history["total"], 1)
            self.assertTrue(history["experiments" if kind == "experiment" else "drafts"][0]["is_archived"])
            detail = self.client.get(f"{roots[kind]}{object_id}/")
            self.assertEqual(detail.status_code, 200)
            self.assertTrue(detail.json()["is_archived"])
            if kind == "experiment":
                restored = {**data, "revision": 2, "is_archived": False,
                            "request_id": "20000000-0000-4000-8000-000000000003"}
                self.assert_response_fixture(self.client.post(url, restored, format="json"), "authoring-experiment-restored.json")
                replay = self.assert_response_fixture(self.client.post(url, data, format="json"), "authoring-experiment-archive-replay.json")
                self.assertFalse(replay["is_archived"])
                self.assertEqual(replay["revision"], 3)
                self.assertEqual(replay["operation"], {"is_archived": True, "revision": 2})
