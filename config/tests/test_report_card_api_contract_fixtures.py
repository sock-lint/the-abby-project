"""Report card bodies produced by the real grade capture and correction API."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.chronicle.models import ChronicleEntry, GradeDailyCounter
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rewards.models import CoinLedger
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "report-card-api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class ReportCardApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        super().setUp()
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=shared_fixtures.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Report Card Fixture Family", family_id=31,
            parents=[{"id": 6, "username": "report-card-fixture-parent"}],
            children=[
                {"id": 7, "username": "report-card-fixture-child"},
                {"id": 8, "username": "report-card-fixture-sibling"},
            ],
        )
        self.child, self.sibling = household.children
        self.parent = household.parents[0]
        other = make_family(
            "Other Report Card Fixture Family", family_id=32,
            parents=[{"id": 98, "username": "report-card-fixture-other-parent"}],
            children=[{"id": 99, "username": "report-card-fixture-other-child"}],
        )
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        category = SkillCategory.objects.create(id=21, name="Life Skills")
        self.skill = Skill.objects.create(id=22, name="Time Management", category=category)
        # Pin real endpoint-created IDs after a seeded row, even when a prior
        # PostgreSQL test has advanced this table's nontransactional sequence.
        ChronicleEntry.objects.create(
            id=300, user=self.other_child, kind=ChronicleEntry.Kind.GRADE,
            occurred_on=date(2026, 10, 9), chapter_year=2026,
            title="Other family's result", is_private=False,
            metadata={"grade": {
                "subject": "Math", "assessment": "Class grade",
                "grade_format": "letter", "letter": "A",
            }},
        )
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ChronicleEntry]):
                cursor.execute(sql)
        token = Token.objects.create(user=self.child, key="c" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.submission = {
            "report_card": {
                "period_type": "quarter", "period_number": 1, "school_year": 2026,
                "subjects": [
                    {"subject": "Math", "grade_format": "percentage", "score": "92.500000"},
                    {"subject": "Science", "grade_format": "points", "score": "11.25", "possible": "10.000"},
                    {"subject": "English", "grade_format": "letter", "letter": "A-"},
                ],
            },
            "reflection": "I kept up with my work this quarter.",
            "occurred_on": "2026-10-09", "is_private": True,
            "client_entry_id": "11111111-1111-4111-8111-111111111111",
        }

    def post(self, submission=None):
        return self.client.post(
            "/api/chronicle/grades/", self.submission if submission is None else submission, format="json",
        )

    def test_report_card_renamed_taxonomy_preserves_measured_receipt_and_retry(self):
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        with override_user(self.parent, scopes=frozenset({"mcp:author", "mcp:catalog", "mcp:publish"})):
            for name, params in [
                ("update_category", {"category_id": self.skill.category_id, "name": "Everyday practice"}),
                ("update_skill", {"skill_id": self.skill.pk, "name": "Time planning"}),
            ]:
                result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
                body = result[1] if isinstance(result, tuple) else result.structuredContent
                self.assertNotIn("error", body, body)
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["reward_receipt"]["xp_awarded"], 10)
        created = self.assert_response_fixture(response, "report-card-renamed-taxonomy.json", status=201)
        self.assertEqual(created["reward_receipt"]["skills"], [{
            "skill_id": self.skill.pk, "name": "Time planning", "xp": 10,
        }])
        replay = self.post()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), created)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 10)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_quarter_semester_history_and_correction_preserve_original_recognition(self):
        created = self.assert_response_fixture(self.post(), "report-card-created.json", status=201)
        self.assertEqual(created["kind"], "grade")
        self.assertEqual(created["user"], self.child.pk)
        self.assertNotIn("grade", created["metadata"])
        self.assertEqual(created["metadata"]["report_card"]["subjects"], [
            {"subject": "Math", "grade_format": "percentage", "score": "92.5"},
            {"subject": "Science", "grade_format": "points", "score": "11.25", "possible": "10"},
            {"subject": "English", "grade_format": "letter", "letter": "A-"},
        ])
        self.assertEqual(created["reward_receipt"]["status"], "awarded")
        self.assertEqual(created["reward_receipt"]["xp_awarded"], 10)
        replay = self.post()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), created)

        semester = deepcopy(self.submission)
        semester.update({
            "client_entry_id": "22222222-2222-4222-8222-222222222222",
            "occurred_on": "2026-05-29", "reflection": "A whole semester of learning.",
        })
        semester["report_card"].update({"period_type": "semester", "period_number": 2, "school_year": 2025})
        semester_saved = self.post(semester)
        self.assertEqual(semester_saved.status_code, 201, semester_saved.content)
        self.assertEqual(semester_saved.json()["reward_receipt"]["status"], "daily_limit")
        listed = self.assert_response_fixture(
            self.client.get("/api/chronicle/grades/"), "report-cards-list.json",
        )
        self.assertEqual(listed["count"], 2)
        self.assertEqual(listed["results"], [created, semester_saved.json()])

        corrected_card = deepcopy(created["metadata"]["report_card"])
        corrected_card["subjects"][0]["score"] = "95.000"
        corrected = self.assert_response_fixture(self.client.patch(
            f"/api/chronicle/{created['id']}/grade/", {
                "report_card": corrected_card, "reflection": "Math was corrected after a missing score.",
                "is_private": False,
            }, format="json",
        ), "report-card-corrected.json")
        self.assertEqual(corrected["metadata"]["report_card"]["subjects"][0]["score"], "95")
        self.assertEqual(corrected["reward_receipt"], created["reward_receipt"])
        self.assertEqual(corrected["metadata"]["request_fingerprint"], created["metadata"]["request_fingerprint"])
        self.assertEqual(self.post().json(), corrected)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 2)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 10)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_unknown_subject_fields_retain_nested_validation_without_writes(self):
        invalid = deepcopy(self.submission)
        invalid["report_card"]["subjects"][0]["xp_awarded"] = 1000
        body = self.assert_response_fixture(
            self.post(invalid), "report-card-invalid.json", status=400,
        )
        self.assertIn("xp_awarded", body["report_card"]["subjects"]["0"])
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(GradeDailyCounter.objects.filter(user=self.child).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

    def test_subject_errors_preserve_original_indices_without_writes(self):
        invalid = deepcopy(self.submission)
        invalid["report_card"]["subjects"][1]["xp_awarded"] = 1000
        invalid["report_card"]["subjects"][2]["coins_awarded"] = 1000
        response = self.post(invalid)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["report_card"]["subjects"], {
            "1": {"xp_awarded": "Unknown field."},
            "2": {"coins_awarded": "Unknown field."},
        })
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(GradeDailyCounter.objects.filter(user=self.child).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())

    def test_report_cards_keep_child_author_and_family_sharing_boundaries(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        saved = response.json()
        entry_url = f"/api/chronicle/{saved['id']}/grade/"
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/chronicle/grades/").json()["results"], [])
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.patch(entry_url, {"is_private": False}, format="json").status_code, 403)
        self.client.force_authenticate(self.child)
        shared = self.client.patch(entry_url, {"is_private": False}, format="json")
        self.assertEqual(shared.status_code, 200, shared.content)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/chronicle/grades/").json()["results"], [shared.json()])
        for reader in (self.sibling, self.other_parent, self.other_child):
            with self.subTest(reader=reader.username):
                self.client.force_authenticate(reader)
                results = self.client.get("/api/chronicle/grades/").json()["results"]
                self.assertNotIn(saved["id"], [entry["id"] for entry in results])
                correction = self.client.patch(entry_url, {"is_private": True}, format="json")
                self.assertEqual(correction.status_code, 403 if reader.role == "parent" else 404)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 10)
