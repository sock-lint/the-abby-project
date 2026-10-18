"""Submission dates are household dates, separate from recurrence identity."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreNotAvailableError, ChoreService
from config.tests.factories import make_family


class ChoreSubmissionTimingTests(TestCase):
    def setUp(self):
        household = make_family(
            parents=[{"username": "timing-parent"}],
            children=[{"username": "timing-child"}, {"username": "timing-sibling"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.client = APIClient()

    def chore(self, **overrides):
        return Chore.objects.create(
            family=self.family, created_by=self.parent, title="Water plants",
            **overrides,
        )

    def submit(self, chore, at):
        self.client.force_authenticate(self.child)
        with patch("django.utils.timezone.now", return_value=at):
            response = self.client.post(f"/api/chores/{chore.pk}/complete/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_friday_submission_keeps_week_identity_but_exposes_actual_day_and_sunday_due(self):
        chore = self.chore(recurrence="weekly")
        at = datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)
        row = self.submit(chore, at)
        self.assertEqual(row["completed_date"], "2026-10-12")
        self.assertEqual(row["timing_snapshot"], {
            "version": 1, "timezone": "America/Phoenix",
            "submitted_at": at.isoformat(), "submitted_on": "2026-10-16",
            "schedule": "weekly", "period_start": "2026-10-12",
            "period_end": "2026-10-18", "due_on": "2026-10-18",
            "timeliness": "on_time",
        })

    def test_tokyo_monday_midnight_sets_period_and_availability_using_family_date(self):
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        chore = self.chore(recurrence="weekly")
        at = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
        row = self.submit(chore, at)
        self.assertEqual(row["completed_date"], "2026-10-19")
        self.assertEqual(row["timing_snapshot"]["submitted_on"], "2026-10-19")
        self.assertEqual(row["timing_snapshot"]["due_on"], "2026-10-25")
        with patch("django.utils.timezone.now", return_value=at):
            available = ChoreService.get_available_chores(self.child)
        self.assertEqual(len(available), 1)
        self.assertTrue(available[0].is_done_today)

    def test_daily_snapshot_uses_family_day_and_includes_that_whole_day(self):
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        row = self.submit(self.chore(), datetime(2026, 10, 18, 15, 1, tzinfo=timezone.utc))
        self.assertEqual(row["completed_date"], "2026-10-19")
        snapshot = row["timing_snapshot"]
        for key in ("submitted_on", "period_start", "period_end", "due_on"):
            self.assertEqual(snapshot[key], "2026-10-19")
        self.assertEqual(snapshot["timeliness"], "on_time")

    def test_weekly_sunday_end_is_inclusive(self):
        row = self.submit(
            self.chore(recurrence="weekly"),
            datetime(2026, 10, 19, 6, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(row["timing_snapshot"]["submitted_on"], "2026-10-18")
        self.assertEqual(row["timing_snapshot"]["due_on"], "2026-10-18")
        self.assertEqual(row["timing_snapshot"]["timeliness"], "on_time")

    def test_one_time_deadline_is_optional_and_inclusive(self):
        at = datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)
        for due, expected in [
            (None, None), (date(2026, 10, 15), "late"),
            (date(2026, 10, 16), "on_time"), (date(2026, 10, 17), "on_time"),
        ]:
            with self.subTest(due=due):
                row = self.submit(self.chore(recurrence="one_time", due_date=due), at)
                snapshot = row["timing_snapshot"]
                self.assertIsNone(snapshot["period_start"])
                self.assertIsNone(snapshot["period_end"])
                self.assertEqual(snapshot["due_on"], due.isoformat() if due else None)
                self.assertEqual(snapshot["timeliness"], expected)

    def test_review_and_schedule_edits_do_not_rewrite_submission_evidence(self):
        chore = self.chore(recurrence="weekly")
        row = self.submit(chore, datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc))
        chore.recurrence = "one_time"
        chore.due_date = date(2026, 10, 15)
        chore.save(update_fields=["recurrence", "due_date"])
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        self.client.force_authenticate(self.parent)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 22, 18, tzinfo=timezone.utc)):
            response = self.client.post(f"/api/chore-completions/{row['id']}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        completion = ChoreCompletion.objects.get(pk=row["id"])
        self.assertEqual(completion.timing_snapshot, row["timing_snapshot"])
        self.assertEqual(response.json()["timing_snapshot"], row["timing_snapshot"])
        self.assertEqual(completion.decided_at.date(), date(2026, 10, 22))

    def test_submission_freezes_the_current_deadline_when_caller_has_an_older_chore(self):
        chore = self.chore(recurrence="one_time", due_date=date(2026, 10, 18))
        Chore.objects.filter(pk=chore.pk).update(due_date=date(2026, 10, 15))
        at = datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            completion = ChoreService.submit_completion(self.child, chore)
        self.assertEqual(completion.timing_snapshot["due_on"], "2026-10-15")
        self.assertEqual(completion.timing_snapshot["timeliness"], "late")

    def test_legacy_completion_stays_unknown_when_reviewed(self):
        completion = self.completion(self.child, "pending", date(2026, 10, 12))
        self.client.force_authenticate(self.parent)
        response = self.client.post(f"/api/chore-completions/{completion.pk}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["timing_snapshot"])
        completion.refresh_from_db()
        self.assertIsNone(completion.timing_snapshot)

    def test_dst_repeated_hour_does_not_allow_a_second_daily_completion(self):
        self.family.timezone = "America/New_York"
        self.family.save(update_fields=["timezone"])
        chore = self.chore()
        row = self.submit(chore, datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))
        self.assertEqual(row["timing_snapshot"]["submitted_on"], "2026-11-01")
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ChoreNotAvailableError, "already completed"):
                ChoreService.submit_completion(self.child, chore)

    def test_dst_spring_forward_keeps_daily_deadline_on_the_local_date(self):
        self.family.timezone = "America/New_York"
        self.family.save(update_fields=["timezone"])
        for hour, minute in [(6, 59), (7, 1)]:
            with self.subTest(hour=hour, minute=minute):
                row = self.submit(self.chore(), datetime(2026, 3, 8, hour, minute, tzinfo=timezone.utc))
                self.assertEqual(row["timing_snapshot"]["submitted_on"], "2026-03-08")
                self.assertEqual(row["timing_snapshot"]["due_on"], "2026-03-08")
                self.assertEqual(row["timing_snapshot"]["timeliness"], "on_time")

    def test_complete_ignores_client_backdating_and_forged_timing(self):
        chore = self.chore(recurrence="weekly")
        self.client.force_authenticate(self.child)
        at = datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            response = self.client.post(f"/api/chores/{chore.pk}/complete/", {
                "completed_date": "2026-01-01",
                "timing_snapshot": {"submitted_on": "2026-01-01", "timeliness": "on_time"},
                "due_date": "2099-01-01",
            }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["completed_date"], "2026-10-12")
        self.assertEqual(response.json()["timing_snapshot"]["submitted_on"], "2026-10-16")
        self.assertEqual(response.json()["timing_snapshot"]["due_on"], "2026-10-18")

    def test_rest_deadline_writes_accept_only_one_time_and_clear_recurrence_edits(self):
        self.client.force_authenticate(self.parent)
        for recurrence in ["daily", "weekly"]:
            with self.subTest(recurrence=recurrence):
                response = self.client.post("/api/chores/", {
                    "title": "Invalid deadline", "recurrence": recurrence, "due_date": "2026-10-18",
                }, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("due_date", response.json())
        response = self.client.post("/api/chores/", {
            "title": "One-time", "recurrence": "one_time", "due_date": "2026-10-18",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        chore = Chore.objects.get(title="One-time")
        self.assertEqual(chore.due_date, date(2026, 10, 18))
        read = self.client.get(f"/api/chores/{chore.pk}/")
        self.assertEqual(read.json()["due_date"], "2026-10-18")
        response = self.client.patch(f"/api/chores/{chore.pk}/", {"recurrence": "weekly"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        chore.refresh_from_db()
        self.assertIsNone(chore.due_date)
        response = self.client.patch(f"/api/chores/{chore.pk}/", {"due_date": "2026-10-18"}, format="json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_proposal_approval_validates_deadline_and_can_clear_it_with_recurrence(self):
        chore = self.chore(recurrence="one_time", due_date=date(2026, 10, 18),
                           pending_parent_review=True)
        self.client.force_authenticate(self.parent)
        response = self.client.post(f"/api/chores/{chore.pk}/approve/", {
            "recurrence": "daily", "due_date": "2026-10-18",
        }, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        chore.refresh_from_db()
        self.assertTrue(chore.pending_parent_review)
        response = self.client.post(f"/api/chores/{chore.pk}/approve/", {
            "recurrence": "daily",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        chore.refresh_from_db()
        self.assertFalse(chore.pending_parent_review)
        self.assertIsNone(chore.due_date)

    def completion(self, user, status, completed_date, chore=None):
        return ChoreCompletion.objects.create(
            chore=chore or self.chore(), user=user, status=status, completed_date=completed_date,
            reward_amount_snapshot="0.00", coin_reward_snapshot=0,
        )

    def test_reviewed_history_is_paginated_and_filters_exact_child_without_pending_rows(self):
        chore = self.chore()
        ChoreCompletion.objects.bulk_create([
            ChoreCompletion(
                chore=chore, user=self.child, status="approved" if index % 2 else "rejected",
                completed_date=date(2026, 1, 1) + timedelta(days=index),
                reward_amount_snapshot="0.00", coin_reward_snapshot=0,
            ) for index in range(55)
        ])
        # Identical timestamps need a stable secondary order across pages.
        ChoreCompletion.objects.filter(chore=chore).update(
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.completion(self.child, "pending", date(2026, 10, 1))
        self.completion(self.sibling, "approved", date(2026, 10, 2))
        other = make_family("Elsewhere", children=[{"username": "timing-foreign"}])
        self.completion(other.children[0], "approved", date(2026, 10, 3))
        self.client.force_authenticate(self.parent)
        response = self.client.get(f"/api/chore-completions/?status=reviewed&user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["count"], 55)
        self.assertIsNotNone(payload["next"])
        self.assertTrue(all(row["user"] == self.child.pk for row in payload["results"]))
        self.assertEqual({row["status"] for row in payload["results"]}, {"approved", "rejected"})
        expected_ids = list(ChoreCompletion.objects.filter(chore=chore).order_by("-pk").values_list("pk", flat=True))
        self.assertEqual([row["id"] for row in payload["results"]], expected_ids[:20])
        page_two = self.client.get(f"/api/chore-completions/?status=reviewed&user_id={self.child.pk}&page=2")
        self.assertEqual(page_two.status_code, 200, page_two.content)
        self.assertEqual([row["id"] for row in page_two.json()["results"]], expected_ids[20:40])

    def test_history_filter_rejects_invalid_and_foreign_ids_without_leaking_rows(self):
        other = make_family("Elsewhere", children=[{"username": "timing-foreign"}])
        self.client.force_authenticate(self.parent)
        for invalid in ["", "abc", "1.5", "0", "-1", "999999999999999999999999"]:
            with self.subTest(invalid=invalid):
                response = self.client.get("/api/chore-completions/", {"status": "reviewed", "user_id": invalid})
                self.assertEqual(response.status_code, 400, response.content)
        for inaccessible in [other.children[0].pk, self.parent.pk, 999999]:
            with self.subTest(inaccessible=inaccessible):
                response = self.client.get("/api/chore-completions/", {"status": "reviewed", "user_id": inaccessible})
                self.assertEqual(response.status_code, 404, response.content)
        self.completion(self.child, "approved", date(2026, 10, 1))
        self.completion(self.sibling, "approved", date(2026, 10, 1))
        self.client.force_authenticate(self.child)
        own = self.client.get("/api/chore-completions/", {"status": "reviewed", "user_id": self.child.pk})
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(own.json()["count"], 1)
        sibling = self.client.get("/api/chore-completions/", {"user_id": self.sibling.pk})
        self.assertEqual(sibling.status_code, 404, sibling.content)

    def test_history_excludes_foreign_chore_even_if_completion_user_is_local(self):
        other = make_family("Elsewhere", parents=[{"username": "timing-foreign-parent"}])
        foreign_chore = Chore.objects.create(family=other.family, created_by=other.parents[0], title="Foreign")
        self.completion(self.child, "approved", date(2026, 10, 1), chore=foreign_chore)
        self.client.force_authenticate(self.parent)
        response = self.client.get("/api/chore-completions/?status=reviewed")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)

    def test_reviewed_history_distinguishes_frozen_deadline_from_edited_or_cleared_current_date(self):
        self.client.force_authenticate(self.parent)
        for status, current_due in [("approved", date(2026, 10, 22)), ("rejected", None)]:
            with self.subTest(status=status, current_due=current_due):
                chore = self.chore(recurrence="one_time", due_date=date(2026, 10, 18))
                at = datetime(2026, 10, 17, 18, tzinfo=timezone.utc)
                with patch("django.utils.timezone.now", return_value=at):
                    completion = ChoreService.submit_completion(self.child, chore)
                ChoreCompletion.objects.filter(pk=completion.pk).update(status=status)
                Chore.objects.filter(pk=chore.pk).update(due_date=current_due)
                response = self.client.get(f"/api/chore-completions/?status=reviewed&user_id={self.child.pk}")
                self.assertEqual(response.status_code, 200, response.content)
                row = next(item for item in response.json()["results"] if item["id"] == completion.pk)
                self.assertEqual(row["timing_snapshot"]["due_on"], "2026-10-18")
                self.assertEqual(row["current_due_date"], current_due.isoformat() if current_due else None)

