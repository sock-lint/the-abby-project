"""Saved homework days survive timezone changes and challenge fact replay."""
from datetime import date, datetime, timezone as dt_timezone
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.homework.services import HomeworkService
from apps.quests.activity import record_activity, resolve_activity
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeActivity, ChallengeContribution, DailyBonus
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


def proof():
    image = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(image, format="PNG")
    return SimpleUploadedFile("homework-proof.png", image.getvalue(), content_type="image/png")


@override_settings(
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HomeworkChallengeActivityDateTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        household = make_family(
            "Homework activity dates",
            parents=[{"username": "activity-date-parent"}],
            children=[{"username": "activity-date-child"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child = household.children[0]
        self.set_zone("America/Phoenix")

    def set_zone(self, name):
        self.family.timezone = name
        self.family.save(update_fields=["timezone"])
        self.child.refresh_from_db()
        self.parent.refresh_from_db()

    def submit(self, at):
        assignment = HomeworkAssignment.objects.create(
            title="Read a chapter", subject="reading", due_date=date(2026, 10, 25),
            assigned_to=self.child, created_by=self.parent,
        )
        with patch("django.utils.timezone.now", return_value=at):
            return HomeworkService.submit_completion(self.child, assignment, [proof()])

    def approve(self, submission, at, *, record_challenges=True):
        with patch("django.utils.timezone.now", return_value=at):
            if record_challenges:
                HomeworkService.approve_submission(submission, self.parent)
            else:
                # Model a saved approval whose downstream game-loop dispatch
                # was unavailable, so a later parent goal must scan the source.
                with patch("apps.rpg.services.GameLoopService.on_task_completed"):
                    HomeworkService.approve_submission(submission, self.parent)
        submission.refresh_from_db()

    def goal(self, at, name="Approved homework this week"):
        with patch("django.utils.timezone.now", return_value=at):
            return create_goal(self.parent, self.child, {
                "name": name, "trigger_type": "homework_complete", "metric": "count",
                "target": 1, "unit": "actions", "period": "this_week", "repeat_weekly": True,
                "coin_reward": 7, "xp_reward": 0, "skill_tags": [],
            })

    def fact(self, submission):
        return ChallengeActivity.objects.get(
            user=self.child, source_type="homework_complete", source_id=str(submission.pk),
            trigger_type="homework_complete",
        )

    def test_approval_after_timezone_change_keeps_original_submission_week(self):
        goal = self.goal(datetime(2026, 10, 18, 17, tzinfo=dt_timezone.utc))
        submission = self.submit(datetime(2026, 10, 18, 20, tzinfo=dt_timezone.utc))
        self.assertEqual(submission.timing_snapshot["submitted_on"], "2026-10-18")
        original_snapshot = dict(submission.timing_snapshot)
        self.set_zone("Asia/Tokyo")
        approved_at = datetime(2026, 10, 19, 18, tzinfo=dt_timezone.utc)

        self.approve(submission, approved_at)

        fact = self.fact(submission)
        self.assertEqual(fact.occurred_on, date(2026, 10, 18))
        self.assertEqual(fact.occurred_at, approved_at)
        self.assertEqual(fact.occurred_at, submission.decided_at)
        self.assertEqual(submission.timing_snapshot, original_snapshot)
        # The accepted-day daily bonus remains distinct from the original
        # submission week: approval is already October 20 in Tokyo.
        self.assertEqual(DailyBonus.objects.get(user=self.child).date, date(2026, 10, 20))
        goal.refresh_from_db()
        self.assertEqual((goal.progress, goal.status), (1, "completed"))
        self.assertEqual(goal.goal.timezone_name, "America/Phoenix")
        self.assertEqual(list(ChallengeContribution.objects.filter(activity=fact).values_list(
            "occurrence_id", flat=True,
        )), [goal.pk])

    def test_backfill_includes_saved_monday_even_when_timestamp_precedes_new_timezone_week(self):
        self.set_zone("Asia/Tokyo")
        submission = self.submit(datetime(2026, 10, 18, 15, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(submission.timing_snapshot["submitted_on"], "2026-10-19")
        self.set_zone("America/Phoenix")
        approved_at = datetime(2026, 10, 19, 18, tzinfo=dt_timezone.utc)
        self.approve(submission, approved_at, record_challenges=False)
        self.assertFalse(ChallengeActivity.objects.filter(source_type="homework_complete").exists())

        goal = self.goal(datetime(2026, 10, 19, 19, tzinfo=dt_timezone.utc))

        self.assertLess(submission.created_at, goal.starts_at)
        fact = self.fact(submission)
        self.assertEqual((fact.occurred_on, fact.occurred_at), (date(2026, 10, 19), approved_at))
        self.assertEqual((goal.progress, goal.status), (1, "completed"))
        self.assertEqual(ChallengeContribution.objects.filter(occurrence=goal, activity=fact).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(
            user=self.child, description=f"Challenge complete: {goal.goal.name}",
        ).count(), 1)

    def test_backfill_excludes_saved_sunday_inside_new_timezone_monday_timestamp_window(self):
        submission = self.submit(datetime(2026, 10, 18, 20, tzinfo=dt_timezone.utc))
        self.assertEqual(submission.timing_snapshot["submitted_on"], "2026-10-18")
        self.set_zone("Asia/Tokyo")
        self.approve(
            submission, datetime(2026, 10, 19, 18, tzinfo=dt_timezone.utc), record_challenges=False,
        )

        goal = self.goal(datetime(2026, 10, 19, 19, tzinfo=dt_timezone.utc))

        self.assertGreaterEqual(submission.created_at, goal.starts_at)
        self.assertLess(submission.created_at, goal.ends_at)
        self.assertEqual((goal.progress, goal.status), (0, "active"))
        self.assertFalse(ChallengeContribution.objects.filter(occurrence=goal).exists())
        self.assertFalse(CoinLedger.objects.filter(
            user=self.child, description=f"Challenge complete: {goal.goal.name}",
        ).exists())

    def test_legacy_or_invalid_snapshot_uses_default_timezone_instead_of_current_household(self):
        submitted_at = datetime(2026, 10, 18, 20, tzinfo=dt_timezone.utc)
        approved_at = datetime(2026, 10, 19, 18, tzinfo=dt_timezone.utc)
        for snapshot in [
            None, {}, {"version": 2, "schedule": "homework", "submitted_on": "2026-10-19"},
            {"version": 1, "schedule": "weekly", "submitted_on": "2026-10-19"},
            {"version": 1, "schedule": "homework", "submitted_on": "2026-02-30"},
            {"version": 1, "schedule": "homework", "submitted_on": 19},
            {"version": 1, "schedule": "homework", "submitted_on": "2026-10-19T00:00:00"},
        ]:
            with self.subTest(snapshot=snapshot):
                submission = self.submit(submitted_at)
                HomeworkSubmission.objects.filter(pk=submission.pk).update(timing_snapshot=snapshot)
                self.approve(submission, approved_at, record_challenges=False)
                self.set_zone("Asia/Tokyo")
                # An activated browser/request timezone is also not evidence
                # about the original timezone of a pre-snapshot submission.
                with timezone.override("Pacific/Auckland"):
                    data = resolve_activity(self.child, "homework_complete", {"submission_id": submission.pk})
                self.assertEqual(data["occurred_on"], date(2026, 10, 18))
                self.assertEqual(data["occurred_at"], approved_at)
                self.assertEqual(data["source_id"], str(submission.pk))

    def test_replay_preserves_existing_fact_and_does_not_duplicate_its_reward(self):
        goal = self.goal(datetime(2026, 10, 18, 17, tzinfo=dt_timezone.utc))
        submission = self.submit(datetime(2026, 10, 18, 20, tzinfo=dt_timezone.utc))
        approved_at = datetime(2026, 10, 19, 18, tzinfo=dt_timezone.utc)
        self.approve(submission, approved_at, record_challenges=False)
        # Existing persisted facts predate this resolver change and must never
        # be moved, even if their day differs from the newer source snapshot.
        existing = ChallengeActivity.objects.create(
            user=self.child, source_type="homework_complete", source_id=str(submission.pk),
            trigger_type="homework_complete", occurred_on=date(2026, 10, 17), occurred_at=approved_at,
            context={"assignment_id": submission.assignment_id, "on_time": True, "skill_tags": []},
        )
        self.set_zone("Asia/Tokyo")
        with patch("django.utils.timezone.now", return_value=approved_at):
            record_activity(self.child, "homework_complete", {"submission_id": submission.pk})
        existing.refresh_from_db()
        original_context = dict(existing.context)
        self.set_zone("Pacific/Auckland")

        for _ in range(2):
            with patch("django.utils.timezone.now", return_value=approved_at):
                record_activity(self.child, "homework_complete", {"submission_id": submission.pk})

        existing.refresh_from_db()
        goal.refresh_from_db()
        self.assertEqual((existing.occurred_on, existing.occurred_at), (date(2026, 10, 17), approved_at))
        self.assertEqual(existing.context, original_context)
        self.assertEqual(self.fact(submission).pk, existing.pk)
        self.assertEqual((goal.progress, goal.status), (1, "completed"))
        self.assertEqual(ChallengeContribution.objects.filter(activity=existing).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(
            user=self.child, description=f"Challenge complete: {goal.goal.name}",
        ).count(), 1)
