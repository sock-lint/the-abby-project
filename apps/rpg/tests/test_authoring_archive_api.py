"""Native archive errors and read-only enforcement use the shared domain service."""
from uuid import uuid4

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.rpg.models import ProgressionExperiment, RPGContentDraft, RPGEditorialDraft
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringArchiveApiTests(APITestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "native-archive", "is_staff": True}]).parents[0]
        self.other = make_family(parents=[{"username": "native-other", "is_staff": True}]).parents[0]
        self.client.force_authenticate(self.actor)

    def rows(self):
        for kind, model, root in (
            ("content", RPGContentDraft, "/api/rpg/content-workbench/drafts/"),
            ("editorial", RPGEditorialDraft, "/api/rpg/editorial/drafts/"),
            ("experiment", ProgressionExperiment, "/api/rpg/progression-lab/experiments/"),
        ):
            values = {"actor": self.actor, "family": self.actor.family, "name": "Private saved work"}
            if kind == "editorial":
                values["section"] = "affirmations"
            row = model.objects.create(**values)
            yield kind, row, f"{root}{row.pk}/", root

    def test_confirmation_strict_types_and_native_conflicts_do_not_mutate(self):
        for kind, row, detail, _ in self.rows():
            with self.subTest(kind=kind):
                data = {"revision": 1, "is_archived": True, "request_id": str(uuid4()), "confirmation": True}
                for invalid in ({"confirmation": False}, {"revision": True}, {"is_archived": "true"},
                                {"request_id": "invalid"}):
                    self.assertEqual(self.client.post(f"{detail}archive/", {**data, **invalid}, format="json").status_code, 400)
                row.refresh_from_db()
                self.assertEqual((row.is_archived, row.revision), (False, 1))
                self.assertEqual(self.client.post(f"{detail}archive/", data, format="json").status_code, 200)
                changed = self.client.post(f"{detail}archive/", {**data, "is_archived": False}, format="json")
                self.assertEqual(changed.status_code, 409)
                self.assertEqual(changed.json()["code"], "idempotency_conflict")
                stale = self.client.post(f"{detail}archive/", {**data, "request_id": str(uuid4())}, format="json")
                self.assertEqual(stale.status_code, 409)
                row.refresh_from_db()
                self.assertEqual((row.is_archived, row.revision), (True, 2))

    def test_other_authors_and_query_targeting_cannot_access_archives(self):
        for kind, row, detail, root in self.rows():
            with self.subTest(kind=kind):
                data = {"revision": 1, "is_archived": True, "request_id": str(uuid4()), "confirmation": True}
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.post(f"{detail}archive/", data, format="json").status_code, 404)
                self.client.force_authenticate(self.actor)
                self.assertEqual(self.client.get(root, {"include_archived": "true", "user_id": self.other.pk}).status_code, 400)
                self.assertEqual(self.client.get(root, {"include_archived": "true", "after": "invalid"}).status_code, 400)
                self.assertEqual(self.client.get(root, {"include_archived": "yes"}).status_code, 400)
                self.assertEqual(self.client.get(root, {"limit": 101}).status_code, 400)
                self.assertEqual(self.client.post(f"{detail}archive/?user_id={self.other.pk}", data, format="json").status_code, 400)
                row.refresh_from_db()
                self.assertFalse(row.is_archived)

    def test_archived_native_content_and_notebook_writes_return_conflicts(self):
        for kind, row, detail, _ in self.rows():
            archived = self.client.post(f"{detail}archive/", {"revision": 1, "is_archived": True,
                "request_id": str(uuid4()), "confirmation": True}, format="json")
            self.assertEqual(archived.status_code, 200)
            if kind == "content":
                self.assertEqual(self.client.patch(detail, {"revision": 2, "changes": []}, format="json").status_code, 409)
                self.assertEqual(self.client.post(f"{detail}preview/", {"revision": 2}, format="json").status_code, 409)
            elif kind == "experiment":
                self.assertEqual(self.client.patch(detail, {"revision": 2, "name": "No mutation", "hypothesis": "No mutation",
                    "config": {}, "candidate_daily_coins": 0, "targets": []}, format="json").status_code, 409)
                self.assertEqual(self.client.post(f"{detail}compare/", {"revision": 2}, format="json").status_code, 409)
                self.assertEqual(self.client.post(f"{detail}observations/", {"revision": 2}, format="json").status_code, 409)
            row.refresh_from_db()
            self.assertEqual(row.revision, 2)
