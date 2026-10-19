"""Synthetic submission dates are actual family-scoped endpoint responses."""
from datetime import date, datetime, timezone
from unittest.mock import patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.homework.services import HomeworkService
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


SUBMITTED = datetime(2026, 10, 23, 16, 30, tzinfo=timezone.utc)
REVIEWED = datetime(2026, 10, 26, 18, tzinfo=timezone.utc)
PROOF_URL = "https://drive.google.com/file/d/synthetic-homework-proof/view?usp=sharing"


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class SubmissionTimingApiFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=SUBMITTED)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Submission Timing Fixture", family_id=71,
            parents=[{"id": 6, "username": "timing-parent"}],
            children=[{"id": 7, "username": "timing-child", "display_name": "Abby"}],
        )
        self.family, self.parent, self.child = household.family, household.parents[0], household.children[0]
        self.family.timezone = "America/New_York"
        self.family.save(update_fields=["timezone"])
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ChoreCompletion, HomeworkSubmission, HomeworkProof]):
                cursor.execute(sql)

    def test_weekly_period_and_friday_submission_survive_later_parent_review(self):
        chore = Chore.objects.create(
            id=21, family=self.family, created_by=self.parent, assigned_to=self.child,
            title="Tidy the desk", recurrence="weekly", xp_reward=0,
        )
        self.client.force_authenticate(self.child)
        pending = self.assert_response_fixture(
            self.client.post(f"/api/chores/{chore.pk}/complete/", {"notes": "Finished Friday"}),
            "completion-timing-weekly-pending.json", status=201,
        )
        self.assertEqual(pending["completed_date"], "2026-10-19")
        self.assertEqual(pending["timing_snapshot"]["submitted_on"], "2026-10-23")
        self.assertEqual(pending["timing_snapshot"]["due_on"], "2026-10-25")
        self.client.force_authenticate(self.parent)
        with patch("django.utils.timezone.now", return_value=REVIEWED):
            self.assertEqual(self.client.post(f"/api/chore-completions/{pending['id']}/approve/").status_code, 200)
        reviewed = self.assert_response_fixture(
            self.client.get("/api/chore-completions/", {"status": "reviewed", "user_id": self.child.pk}),
            "completion-timing-chore-reviewed.json",
        )
        self.assertEqual(reviewed["results"][0]["timing_snapshot"], pending["timing_snapshot"])

    def test_homework_saved_lateness_and_due_date_survive_a_due_date_edit_and_approval(self):
        assignment = HomeworkAssignment.objects.create(
            id=31, created_by=self.parent, assigned_to=self.child,
            title="Reading worksheet", subject="reading", due_date=date(2026, 10, 22),
        )
        # An existing synthetic path keeps this response fixture independent of
        # storage naming. Actual upload validation is covered by homework tests.
        submission = HomeworkService.submit_completion(
            self.child, assignment, images=["homework_proofs/synthetic-timing.png"], notes="Read two chapters",
        )
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(due_date=date(2026, 10, 24))
        self.client.force_authenticate(self.parent)
        with patch("django.utils.timezone.now", return_value=REVIEWED):
            self.assertEqual(self.client.post(f"/api/homework-submissions/{submission.pk}/approve/").status_code, 200)
        reviewed = self.assert_response_fixture(
            self.client.get("/api/homework-submissions/", {"status": "reviewed", "user_id": self.child.pk}),
            "completion-timing-homework-reviewed.json",
        )
        row = reviewed["results"][0]
        self.assertEqual(row["timing_snapshot"]["due_on"], "2026-10-22")
        self.assertEqual(row["current_due_date"], "2026-10-24")
        self.assertEqual(row["timeliness"], "late")
        self.client.force_authenticate(self.child)
        detail = self.assert_response_fixture(
            self.client.get(f"/api/homework/{assignment.pk}/"),
            "completion-timing-homework-assignment.json",
        )
        self.assertEqual(detail["timeliness_preview"]["timeliness"], "on_time")
        self.assertEqual(detail["submission_status"]["timeliness"], "late")

    def test_link_only_homework_proof_survives_review_and_keeps_original_timing(self):
        assignment = HomeworkAssignment.objects.create(
            id=32, created_by=self.parent, assigned_to=self.child,
            title="Science report", subject="science", due_date=date(2026, 10, 24),
        )
        self.client.force_authenticate(self.child)
        response = self.client.post(
            f"/api/homework/{assignment.pk}/submit/",
            {"proof_url": PROOF_URL, "notes": "My finished report"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.json())
        pending = self.assert_response_fixture(
            response, "homework-proof-link-submitted.json", status=201,
        )
        self.assertEqual(pending["proof_url"], PROOF_URL)
        self.assertEqual(pending["proofs"], [])
        self.assertEqual(pending["timeliness"], "on_time")
        self.assertEqual(pending["timing_snapshot"]["due_on"], "2026-10-24")

        # A later deadline edit and approval must preserve both the submitted
        # link and the original on-time classification from the day before.
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(due_date=date(2026, 10, 22))
        self.client.force_authenticate(self.parent)
        with patch("django.utils.timezone.now", return_value=REVIEWED):
            self.assertEqual(self.client.post(f"/api/homework-submissions/{pending['id']}/approve/").status_code, 200)
        reviewed = self.assert_response_fixture(
            self.client.get("/api/homework-submissions/", {"status": "reviewed", "user_id": self.child.pk}),
            "homework-proof-link-reviewed.json",
        )["results"][0]
        self.assertEqual(reviewed["proof_url"], PROOF_URL)
        self.assertEqual(reviewed["proofs"], [])
        self.assertEqual(reviewed["current_due_date"], "2026-10-22")
        self.assertEqual(reviewed["timing_snapshot"], pending["timing_snapshot"])
        self.assertEqual(reviewed["timeliness"], pending["timeliness"])
        self.client.force_authenticate(self.child)
        detail = self.client.get(f"/api/homework-submissions/{pending['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["proof_url"], PROOF_URL)
        self.assertEqual(detail.json()["timing_snapshot"], pending["timing_snapshot"])
