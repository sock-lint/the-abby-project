"""Term report cards preserve complete results without multiplying recognition."""
from copy import deepcopy
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.chronicle.models import ChronicleEntry, GradeDailyCounter
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import ListChronicleEntriesIn
from apps.mcp_server.tools.chronicle import list_chronicle_entries
from config.tests.factories import make_family


class ReportCardAPITests(APITestCase):
    def setUp(self):
        family = make_family(parents=[{"username": "mom"}], children=[{"username": "abby"}, {"username": "sibling"}])
        other = make_family("Other", parents=[{"username": "outside-parent"}], children=[{"username": "outside-child"}])
        self.child, self.sibling = family.children
        self.parent = family.parents[0]
        self.outside_parent, self.outside_child = other.parents[0], other.children[0]
        category = SkillCategory.objects.create(name="Life Skills")
        self.skill = Skill.objects.create(category=category, name="Time Management")
        self.client.force_authenticate(self.child)
        self.payload = {
            "report_card": {
                "period_type": "quarter", "period_number": 1, "school_year": 2025,
                "subjects": [
                    {"subject": " Math ", "grade_format": "percentage", "score": "82.500000"},
                    {"subject": "Science", "grade_format": "letter", "letter": "A-"},
                    {"subject": "History", "grade_format": "points", "score": "11.250000", "possible": "10.000"},
                ],
            },
            "reflection": "I feel ready for the next term.",
            "client_entry_id": str(uuid4()),
        }
        self.ordinary = {
            "subject": "Math", "assessment": "Quiz", "grade_format": "percentage", "score": "80",
            "client_entry_id": str(uuid4()),
        }

    def post(self, payload=None):
        return self.client.post("/api/chronicle/grades/", self.payload if payload is None else payload, format="json")

    def patch(self, entry_id, payload):
        return self.client.patch(f"/api/chronicle/{entry_id}/grade/", payload, format="json")

    def test_quarter_report_card_saves_one_entry_with_all_normalized_marks(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        row = response.json()
        self.assertEqual(row["kind"], "grade")
        self.assertEqual(row["title"], "Quarter 1 report card · 2025–26")
        self.assertTrue(row["is_private"])
        self.assertEqual(row["summary"], self.payload["reflection"])
        self.assertNotIn("grade", row["metadata"])
        self.assertEqual(row["metadata"]["report_card"], {
            "period_type": "quarter", "period_number": 1, "school_year": 2025,
            "subjects": [
                {"subject": "Math", "grade_format": "percentage", "score": "82.5"},
                {"subject": "Science", "grade_format": "letter", "letter": "A-"},
                {"subject": "History", "grade_format": "points", "score": "11.25", "possible": "10"},
            ],
        })
        self.assertEqual(row["reward_receipt"]["xp_awarded"], 10)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, kind="grade").count(), 1)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 10)

    def test_semester_and_fourth_quarter_are_supported(self):
        for period_type, period_number in (("semester", 2), ("quarter", 4)):
            with self.subTest(period_type=period_type):
                payload = deepcopy(self.payload)
                payload["report_card"].update(period_type=period_type, period_number=period_number)
                payload["client_entry_id"] = str(uuid4())
                response = self.post(payload)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["metadata"]["report_card"]["period_number"], period_number)

    def test_invalid_periods_years_and_missing_fields_do_not_save(self):
        changes = (
            {"period_type": "trimester"}, {"period_number": 0}, {"period_number": 5},
            {"period_type": "semester", "period_number": 3}, {"period_number": "first"},
            {"school_year": 0}, {"school_year": 9999}, {"school_year": 2025.5},
            {"period_type": None}, {"subjects": []}, {"subjects": None},
        )
        for change in changes:
            with self.subTest(change=change):
                payload = deepcopy(self.payload)
                payload["report_card"].update(change)
                self.assertEqual(self.post(payload).status_code, 400)
        for field in ("period_type", "period_number", "school_year", "subjects"):
            payload = deepcopy(self.payload)
            del payload["report_card"][field]
            self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(ChronicleEntry.objects.filter(kind="grade").exists())
        self.assertFalse(GradeDailyCounter.objects.exists())

    def test_report_card_is_bounded_to_thirty_distinct_subjects(self):
        payload = deepcopy(self.payload)
        payload["report_card"]["subjects"] = [
            {"subject": f"Subject {index}", "grade_format": "letter", "letter": "P"}
            for index in range(30)
        ]
        first = self.post(payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(len(first.json()["metadata"]["report_card"]["subjects"]), 30)
        payload["report_card"]["subjects"].append({"subject": "Too many", "grade_format": "letter", "letter": "P"})
        payload["client_entry_id"] = str(uuid4())
        self.assertEqual(self.post(payload).status_code, 400)
        payload["report_card"]["subjects"] = [
            {"subject": "Math", "grade_format": "letter", "letter": "B"},
            {"subject": " math ", "grade_format": "letter", "letter": "A"},
        ]
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertEqual(ChronicleEntry.objects.filter(kind="grade").count(), 1)

    def test_nested_marks_use_existing_validation_and_reject_unknown_fields(self):
        invalid_rows = (
            {"subject": "", "grade_format": "letter", "letter": "A"},
            {"subject": "x" * 81, "grade_format": "letter", "letter": "A"},
            {"subject": "Math", "grade_format": "percentage", "score": "100.01"},
            {"subject": "Math", "grade_format": "percentage", "score": "-1"},
            {"subject": "Math", "grade_format": "percentage", "score": "NaN"},
            {"subject": "Math", "grade_format": "percentage", "score": "50", "letter": "A"},
            {"subject": "Math", "grade_format": "points", "score": "4", "possible": "0"},
            {"subject": "Math", "grade_format": "letter", "letter": "E"},
            {"subject": "Math", "grade_format": "letter"},
            {"subject": "Math", "letter": "A"},
            {"subject": "Math", "grade_format": "letter", "letter": "A", "assessment": "Quarter"},
            {"subject": "Math", "grade_format": "letter", "letter": "A", "xp_awarded": 100},
        )
        for subject in invalid_rows:
            with self.subTest(subject=subject):
                payload = deepcopy(self.payload)
                payload["report_card"]["subjects"] = [subject]
                self.assertEqual(self.post(payload).status_code, 400)
        payload = deepcopy(self.payload)
        payload["report_card"]["school"] = "Unknown field"
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertEqual(self.post({**self.payload, "subject": "Math"}).status_code, 400)
        self.assertEqual(self.post({**self.payload, "reward_receipt": {"xp_awarded": 100}}).status_code, 400)
        self.assertFalse(ChronicleEntry.objects.filter(kind="grade").exists())

    def test_exact_normalized_retry_is_safe_after_midnight_and_corrections(self):
        original = self.post()
        self.assertEqual(original.status_code, 201)
        first = original.json()
        changed = self.patch(first["id"], {
            "report_card": {"period_number": 2}, "is_private": False,
            "occurred_on": (timezone.localdate() - timedelta(days=70)).isoformat(),
        })
        self.assertEqual(changed.status_code, 200)
        payload = deepcopy(self.payload)
        payload["report_card"]["subjects"][0].update(subject="Math", score=82.5)
        tomorrow = timezone.localdate() + timedelta(days=1)
        with mock.patch("apps.chronicle.grade_services.timezone.localdate", return_value=tomorrow):
            replay = self.post(payload)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["id"], first["id"])
        self.assertEqual(replay.json()["metadata"]["report_card"]["period_number"], 2)
        self.assertEqual(replay.json()["reward_receipt"], first["reward_receipt"])
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)

    def test_reused_uuid_conflicts_for_changed_report_or_individual_grade(self):
        first = self.post()
        self.assertEqual(first.status_code, 201)
        payload = deepcopy(self.payload)
        payload["report_card"]["period_number"] = 2
        self.assertEqual(self.post(payload).status_code, 409)
        self.assertEqual(self.post({**self.ordinary, "client_entry_id": self.payload["client_entry_id"]}).status_code, 409)
        ordinary = self.post(self.ordinary)
        self.assertEqual(ordinary.status_code, 201)
        self.assertEqual(self.post({**self.payload, "client_entry_id": self.ordinary["client_entry_id"]}).status_code, 409)
        self.assertEqual(ChronicleEntry.objects.filter(kind="grade").count(), 2)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 2)

    def test_scalar_corrections_keep_subjects_and_full_row_replacement_changes_them(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        first = response.json()
        corrected = self.patch(first["id"], {"report_card": {"period_type": "semester", "school_year": 2024}})
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["title"], "Semester 1 report card · 2024–25")
        self.assertEqual(corrected.json()["metadata"]["report_card"]["subjects"], first["metadata"]["report_card"]["subjects"])
        rows = [{"subject": "Art", "grade_format": "letter", "letter": "P"}]
        replaced = self.patch(first["id"], {"report_card": {"subjects": rows}})
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json()["metadata"]["report_card"]["subjects"], rows)
        self.assertEqual(replaced.json()["metadata"]["report_card"]["period_type"], "semester")
        self.assertEqual(replaced.json()["reward_receipt"], first["reward_receipt"])
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)

    def test_invalid_replacement_and_period_correction_preserve_saved_report(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        first = response.json()
        for report_card in (
            {"subjects": [{"subject": "Math", "score": "90"}]},
            {"subjects": [{"subject": "Math", "grade_format": "percentage"}]},
            {"subjects": []}, {"period_number": 3, "period_type": "semester"},
            {"period_type": "bad"}, {"unknown": "field"},
        ):
            with self.subTest(report_card=report_card):
                self.assertEqual(self.patch(first["id"], {"report_card": report_card}).status_code, 400)
        stored = ChronicleEntry.objects.get(pk=first["id"])
        self.assertEqual(stored.metadata["report_card"], first["metadata"]["report_card"])

    def test_corrections_cannot_switch_between_reports_and_individual_grades(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        report = response.json()
        scalar = self.post(self.ordinary).json()
        self.assertEqual(self.patch(report["id"], {"subject": "Math", "score": "90"}).status_code, 400)
        self.assertEqual(self.patch(scalar["id"], {"report_card": self.payload["report_card"]}).status_code, 400)
        self.assertEqual(self.patch(report["id"], {"client_entry_id": str(uuid4())}).status_code, 400)

    def test_report_and_individual_grades_share_daily_recognition_in_both_orders(self):
        for user, first_payload, second_payload in (
            (self.child, self.payload, self.ordinary), (self.sibling, self.ordinary, self.payload),
        ):
            with self.subTest(user=user.pk):
                self.client.force_authenticate(user)
                first, second = self.post(first_payload), self.post(second_payload)
                self.assertEqual(first.status_code, 201)
                self.assertEqual(second.status_code, 201)
                self.assertEqual(first.json()["reward_receipt"]["xp_awarded"], 10)
                self.assertEqual(second.json()["reward_receipt"]["status"], "daily_limit")
                self.assertEqual(second.json()["reward_receipt"]["xp_awarded"], 0)
                self.assertEqual(GradeDailyCounter.objects.get(user=user).count, 2)
                self.assertEqual(SkillProgress.objects.get(user=user, skill=self.skill).xp_points, 10)

    def test_report_is_authored_only_by_authenticated_child(self):
        response = self.post({**self.payload, "user_id": self.sibling.pk})
        self.assertEqual(response.status_code, 201)
        first = response.json()
        self.assertEqual(first["user"], self.child.pk)
        for child in (self.sibling, self.outside_child):
            self.client.force_authenticate(child)
            self.assertEqual(self.patch(first["id"], {"is_private": False}).status_code, 404)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.patch(first["id"], {"is_private": False}).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.post().status_code, 401)

    def test_private_reports_stay_private_across_reads_and_can_be_shared_with_family(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        first = response.json()
        self.client.force_authenticate(self.parent)
        for url in (f"/api/chronicle/{first['id']}/", f"/api/chronicle/{first['id']}/mark-viewed/"):
            response = self.client.get(url) if url.endswith(f"/{first['id']}/") else self.client.post(url)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"/api/chronicle/grades/?user_id={self.child.pk}").json()["results"], [])
        self.assertEqual(self.client.get(f"/api/chronicle/?user_id={self.child.pk}").json()["results"], [])
        self.assertEqual(self.client.get(f"/api/chronicle/summary/?user_id={self.child.pk}").json()["chapters"], [])
        with override_user(self.parent):
            self.assertEqual(list_chronicle_entries(ListChronicleEntriesIn(user_id=self.child.pk, kind="grade"))["entries"], [])
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get(f"/api/chronicle/{first['id']}/").status_code, 200)
        self.assertEqual(self.patch(first["id"], {"is_private": False}).status_code, 200)
        self.client.force_authenticate(self.parent)
        shared = self.client.get(f"/api/chronicle/grades/?user_id={self.child.pk}").json()["results"]
        self.assertEqual([row["id"] for row in shared], [first["id"]])
        for other in (self.sibling, self.outside_child, self.outside_parent):
            self.client.force_authenticate(other)
            self.assertEqual(self.client.get(f"/api/chronicle/{first['id']}/").status_code, 404)

    def test_shared_report_card_supports_family_replies_without_extra_reward(self):
        response = self.post({**self.payload, "is_private": False})
        self.assertEqual(response.status_code, 201)
        first = response.json()
        self.client.force_authenticate(self.parent)
        url = f"/api/chronicle/entries/{first['id']}/comments/"
        reply = self.client.post(url, {"body": "I like your study plan.", "client_comment_id": str(uuid4())}, format="json")
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.child).count, 1)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.patch(first["id"], {"is_private": True}).status_code, 200)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(url).status_code, 404)
