"""Homework deadlines describe submission, independently of later edits/review."""
from datetime import date, datetime, timezone as dt_timezone
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.homework.serializers import HomeworkSubmissionSerializer
from apps.homework.services import HomeworkService
from config.tests.factories import make_family


def proof():
    output = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return SimpleUploadedFile("synthetic-proof.png", output.getvalue(), content_type="image/png")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HomeworkSubmissionTimingTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        family = make_family("Timing household", parents=[{"username": "timing-parent"}], children=[{"username": "timing-child"}, {"username": "timing-sibling"}])
        self.family = family.family
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        other = make_family("Other timing household", parents=[{"username": "other-timing-parent"}], children=[{"username": "other-timing-child"}])
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def assignment(self, due=date(2026, 10, 18), child=None):
        return HomeworkAssignment.objects.create(
            title="Read a chapter", subject="reading", due_date=due,
            assigned_to=child or self.child, created_by=self.parent,
        )

    def submit(self, assignment, at):
        with patch("django.utils.timezone.now", return_value=at):
            return HomeworkService.submit_completion(self.child, assignment, [proof()])

    def set_zone(self, name):
        self.family.timezone = name
        self.family.save(update_fields=["timezone"])
        # Use the persisted child/family relation that production submission reads.
        self.child.refresh_from_db()

    def test_submission_saves_family_day_and_original_due_date(self):
        self.set_zone("Pacific/Auckland")
        at = datetime(2026, 10, 17, 11, 30, tzinfo=dt_timezone.utc)
        submission = self.submit(self.assignment(), at)
        payload = HomeworkSubmissionSerializer(submission).data
        self.assertEqual(payload["timeliness"], "on_time")
        self.assertEqual(payload["current_due_date"], "2026-10-18")
        self.assertEqual(payload["timing_snapshot"], {
            "version": 1, "timezone": "Pacific/Auckland", "submitted_at": at.isoformat(),
            "submitted_on": "2026-10-18", "schedule": "homework",
            "period_start": None, "period_end": None, "due_on": "2026-10-18", "timeliness": "on_time",
        })

    def test_review_after_deadline_and_assignment_edits_preserves_original_promise(self):
        self.set_zone("America/New_York")
        assignment = self.assignment(due=date(2026, 10, 17))
        submission = self.submit(assignment, datetime(2026, 10, 17, 17, tzinfo=dt_timezone.utc))
        before = HomeworkSubmissionSerializer(submission).data
        self.assertEqual(before["timeliness"], "on_time")
        self.assertIn("timing_snapshot", before)
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(due_date=date(2026, 10, 24))
        self.set_zone("Asia/Tokyo")
        reviewed_at = datetime(2026, 10, 20, 15, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=reviewed_at), patch("apps.rpg.services.GameLoopService.on_task_completed") as game_loop:
            HomeworkService.approve_submission(submission, self.parent)
        submission.refresh_from_db()
        after = HomeworkSubmissionSerializer(submission).data
        self.assertEqual(after["timing_snapshot"], before["timing_snapshot"])
        self.assertEqual(after["timeliness"], "on_time")
        self.assertEqual(after["current_due_date"], "2026-10-24")
        self.assertEqual(submission.decided_at, reviewed_at)
        self.assertTrue(game_loop.call_args.args[2]["on_time"])

    def test_local_midnight_changes_timeliness_using_family_date(self):
        self.set_zone("America/New_York")
        before = self.submit(self.assignment(due=date(2026, 10, 17)), datetime(2026, 10, 18, 3, 59, tzinfo=dt_timezone.utc))
        after = self.submit(self.assignment(due=date(2026, 10, 17)), datetime(2026, 10, 18, 4, 1, tzinfo=dt_timezone.utc))
        self.assertEqual(before.timeliness, "on_time")
        self.assertEqual(after.timeliness, "late")
        self.assertEqual(after.timing_snapshot["submitted_on"], "2026-10-18")

    def test_preview_and_saved_submission_share_the_two_day_on_time_window(self):
        self.set_zone("America/New_York")
        self.client.force_authenticate(self.child)
        cases = [
            (datetime(2026, 10, 17, 3, 59, tzinfo=dt_timezone.utc), "2026-10-16", "early"),
            (datetime(2026, 10, 17, 4, 0, tzinfo=dt_timezone.utc), "2026-10-17", "on_time"),
            (datetime(2026, 10, 19, 3, 59, tzinfo=dt_timezone.utc), "2026-10-18", "on_time"),
            (datetime(2026, 10, 19, 4, 0, tzinfo=dt_timezone.utc), "2026-10-19", "late"),
        ]
        for at, local_day, expected in cases:
            with self.subTest(at=at):
                assignment = self.assignment()
                with patch("django.utils.timezone.now", return_value=at):
                    preview = self.client.get(f"/api/homework/{assignment.pk}/")
                    response = self.client.post(
                        f"/api/homework/{assignment.pk}/submit/",
                        {"images": [proof()]}, format="multipart",
                    )
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(response.status_code, 201)
                saved = HomeworkSubmission.objects.get(pk=response.data["id"])
                self.assertEqual(preview.data["timeliness_preview"]["timeliness"], expected)
                self.assertEqual(response.data["timeliness"], expected)
                self.assertEqual(saved.timeliness, expected)
                self.assertEqual(saved.timing_snapshot["timeliness"], expected)
                self.assertEqual(saved.timing_snapshot["submitted_on"], local_day)
                self.assertEqual(saved.timing_snapshot["due_on"], "2026-10-18")

    def test_dst_repeated_hour_keeps_one_calendar_deadline(self):
        self.set_zone("America/New_York")
        instants = [datetime(2026, 11, 1, hour, 30, tzinfo=dt_timezone.utc) for hour in (5, 6)]
        rows = [self.submit(self.assignment(due=date(2026, 11, 1)), at) for at in instants]
        self.assertEqual([row.timeliness for row in rows], ["on_time", "on_time"])
        self.assertEqual([row.timing_snapshot["submitted_on"] for row in rows], ["2026-11-01", "2026-11-01"])
        self.assertNotEqual(rows[0].timing_snapshot["submitted_at"], rows[1].timing_snapshot["submitted_at"])

    def test_legacy_submission_keeps_unknown_original_deadline_and_saved_label(self):
        assignment = self.assignment()
        row = HomeworkSubmission.objects.create(assignment=assignment, user=self.child, status="approved", timeliness="late")
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(due_date=date(2026, 11, 1))
        row = HomeworkSubmission.objects.select_related("assignment").get(pk=row.pk)
        payload = HomeworkSubmissionSerializer(row).data
        self.assertIsNone(payload["timing_snapshot"])
        self.assertEqual(payload["timeliness"], "late")
        self.assertEqual(payload["current_due_date"], "2026-11-01")

    def test_submission_uses_the_current_deadline_when_caller_has_an_older_assignment(self):
        assignment = self.assignment(due=date(2026, 10, 19))
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(due_date=date(2026, 10, 18))
        row = self.submit(assignment, datetime(2026, 10, 18, 17, tzinfo=dt_timezone.utc))
        self.assertEqual(row.timeliness, "on_time")
        self.assertEqual(row.timing_snapshot["due_on"], "2026-10-18")

    def test_preview_and_planning_lead_use_the_childs_family_day(self):
        self.set_zone("Pacific/Auckland")
        assignment = self.assignment(due=date(2026, 10, 18))
        self.client.force_authenticate(self.child)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 17, 11, 30, tzinfo=dt_timezone.utc)):
            response = self.client.get(f"/api/homework/{assignment.pk}/")
            self.assertEqual(response.data["timeliness_preview"]["timeliness"], "on_time")
            assignment.due_date = date(2026, 10, 20)
            self.assertFalse(HomeworkService.can_self_plan(self.child, assignment))

    def test_homework_dashboard_bucket_agrees_with_local_day_timeliness_preview(self):
        self.set_zone("Asia/Tokyo")
        assignment = self.assignment(due=date(2026, 10, 17))
        self.client.force_authenticate(self.child)
        at = datetime(2026, 10, 17, 15, 30, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            detail = self.client.get(f"/api/homework/{assignment.pk}/")
            dashboard = self.client.get("/api/homework/dashboard/")
        self.assertEqual(detail.data["timeliness_preview"]["timeliness"], "late")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual([row["id"] for row in dashboard.data["overdue"]], [assignment.pk])
        self.assertEqual(dashboard.data["today"], [])
        self.assertEqual(dashboard.data["upcoming"], [])

    def test_creating_due_today_uses_target_child_family_date(self):
        self.set_zone("America/Adak")
        at = datetime(2026, 10, 18, 7, 30, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=at), patch("apps.rpg.services.GameLoopService.on_task_completed"):
            assignment = HomeworkService.create_assignment(self.parent, {
                "title": "Reading due today", "subject": "reading", "assigned_to": self.child,
                "due_date": date(2026, 10, 17),
            })
        self.assertEqual(assignment.due_date, date(2026, 10, 17))

    def test_assignment_timing_contains_only_its_matching_childs_saved_record(self):
        assignment = self.assignment()
        row = self.submit(assignment, datetime(2026, 10, 18, 17, tzinfo=dt_timezone.utc))
        response = self.client.get(f"/api/homework/{assignment.pk}/")
        nested = response.data["submission_status"]
        self.assertEqual(set(nested), {"id", "status", "timeliness", "timing_snapshot", "current_due_date", "created_at", "decided_at"})
        self.assertEqual(nested["timing_snapshot"], row.timing_snapshot)
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(assigned_to=self.sibling)
        response = self.client.get(f"/api/homework/{assignment.pk}/")
        self.assertIsNone(response.data["submission_status"])

    def test_submit_ignores_client_timing_fields(self):
        assignment = self.assignment()
        self.client.force_authenticate(self.child)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 17, tzinfo=dt_timezone.utc)):
            response = self.client.post(f"/api/homework/{assignment.pk}/submit/", {
                "images": [proof()], "timeliness": "early", "timing_snapshot": '{"due_on":"2099-01-01"}',
            }, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["timeliness"], "on_time")
        self.assertEqual(response.data["timing_snapshot"]["due_on"], "2026-10-18")

    def history_row(self, child, status):
        assignment = self.assignment(child=child)
        return HomeworkSubmission.objects.create(assignment=assignment, user=child, status=status, timeliness="on_time")

    def test_reviewed_filter_includes_approved_rejected_and_selected_child_only(self):
        approved = self.history_row(self.child, "approved")
        rejected = self.history_row(self.child, "rejected")
        self.history_row(self.child, "pending")
        self.history_row(self.sibling, "approved")
        self.history_row(self.other_child, "approved")
        response = self.client.get(f"/api/homework-submissions/?status=reviewed&user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertCountEqual([row["id"] for row in response.data["results"]], [approved.pk, rejected.pk])
        self.assertIn("next", response.data)

    def test_history_hides_assignment_details_after_it_moves_outside_the_family(self):
        assignment = self.assignment()
        HomeworkSubmission.objects.create(
            assignment=assignment, user=self.child, status="approved", timeliness="on_time",
        )
        HomeworkAssignment.objects.filter(pk=assignment.pk).update(assigned_to=self.other_child)
        response = self.client.get(f"/api/homework-submissions/?status=reviewed&user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_history_rejects_foreign_child_and_malformed_selection(self):
        for selected in (self.other_child.pk, 999999, "not-a-child"):
            with self.subTest(selected=selected):
                response = self.client.get(f"/api/homework-submissions/?status=reviewed&user_id={selected}")
                self.assertEqual(response.status_code, 404)

    def test_child_history_stays_own_scoped(self):
        own = self.history_row(self.child, "approved")
        self.history_row(self.sibling, "approved")
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/homework-submissions/?status=reviewed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [own.pk])
        response = self.client.get(f"/api/homework-submissions/?status=reviewed&user_id={self.sibling.pk}")
        self.assertEqual(response.status_code, 404)

    def test_reviewed_history_preserves_normal_pagination_and_child_filter(self):
        for _ in range(21):
            self.history_row(self.child, "approved")
        self.history_row(self.sibling, "rejected")
        url = f"/api/homework-submissions/?status=reviewed&user_id={self.child.pk}"
        first = self.client.get(url)
        second = self.client.get(f"{url}&page=2")
        self.assertEqual(first.data["count"], 21)
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(len(first.data["results"]), 20)
        self.assertEqual(len(second.data["results"]), 1)
        self.assertTrue(all(row["user"] == self.child.pk for row in first.data["results"] + second.data["results"]))
        self.assertFalse({row["id"] for row in first.data["results"]} & {row["id"] for row in second.data["results"]})
