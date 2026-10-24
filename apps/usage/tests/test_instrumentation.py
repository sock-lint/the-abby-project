"""Human API outcomes are distinct from rewards, automation and read traffic."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.families.models import LiveTestFamily
from apps.habits.models import Habit, HabitLog
from apps.habits.services import HabitService
from apps.homework.models import HomeworkAssignment
from apps.movement.models import MovementSession, MovementType
from apps.movement.services import MovementSessionService
from apps.projects.models import Project
from apps.reading.models import ReadingBook, ReadingSession
from apps.rewards.models import Reward
from apps.rewards.services import CoinService, RewardService
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import ClockService, TimecardService
from apps.usage.models import UsageEvent
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HumanUsageInstrumentationTests(TestCase):
    def setUp(self):
        household = make_family(
            "Synthetic usage family",
            parents=[{"username": "usage-parent"}, {"username": "usage-coparent"}],
            children=[{"username": "usage-child"}],
        )
        self.family = household.family
        self.parent, self.coparent = household.parents
        self.child = household.children[0]
        other = make_family(
            "Synthetic other family", parents=[{"username": "other-usage-parent"}],
            children=[{"username": "other-usage-child"}],
        )
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def post(self, url, payload=None, expected=201):
        response = self.client.post(url, payload or {}, format="json")
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def chore(self):
        return Chore.objects.create(
            family=self.family, title="Synthetic chore", created_by=self.parent,
            assigned_to=self.child, coin_reward=2, xp_reward=0,
        )

    def book(self):
        return ReadingBook.objects.create(
            user=self.child, title="Synthetic reading book",
            client_request_id=uuid4(), create_payload={},
        )

    def movement_type(self):
        return MovementType.objects.create(name="Synthetic walk", slug="synthetic-walk")

    def project(self, **extra):
        return Project.objects.create(
            title="Synthetic timed project", created_by=self.parent,
            assigned_to=self.child, status="in_progress", **extra,
        )

    def timecard(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        return Timecard.objects.create(
            user=self.child, week_start=week_start, week_end=week_start + timedelta(days=6),
        )

    def event(self, feature, action):
        return UsageEvent.objects.get(feature=feature, action=action)

    def test_chore_counts_child_submission_and_first_parent_approval_once(self):
        chore = self.chore()
        submitted = self.post(f"/api/chores/{chore.pk}/complete/")
        self.post(f"/api/chores/{chore.pk}/complete/", expected=400)
        completion_id = submitted.data["id"]
        self.post(f"/api/chore-completions/{completion_id}/approve/", expected=403)
        self.client.force_authenticate(self.parent)
        self.post(f"/api/chore-completions/{completion_id}/approve/", expected=200)
        self.client.force_authenticate(self.coparent)
        self.post(f"/api/chore-completions/{completion_id}/approve/", expected=200)
        for _ in range(2):
            self.assertEqual(self.client.get("/api/chore-completions/").status_code, 200)
        self.assertEqual(UsageEvent.objects.count(), 2)
        self.assertEqual(self.event("chores", "submitted").actor_id, self.child.pk)
        self.assertEqual(self.event("chores", "approved").actor_id, self.parent.pk)

    def test_api_retry_of_automation_approval_does_not_invent_human_activity(self):
        completion = ChoreService.submit_completion(self.child, self.chore())
        ChoreService.approve_completion(completion, self.parent)
        self.client.force_authenticate(self.parent)
        self.post(f"/api/chore-completions/{completion.pk}/approve/", expected=200)
        self.assertFalse(UsageEvent.objects.exists())

    def test_first_human_approval_of_old_work_is_measured_today(self):
        completion = ChoreService.submit_completion(self.child, self.chore())
        ChoreCompletion.objects.filter(pk=completion.pk).update(
            created_at=timezone.now() - timedelta(days=120),
        )
        self.client.force_authenticate(self.parent)
        self.post(f"/api/chore-completions/{completion.pk}/approve/", expected=200)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(self.event("chores", "approved").actor_id, self.parent.pk)

    def test_homework_requires_saved_proof_then_counts_approval_separately(self):
        assignment = HomeworkAssignment.objects.create(
            title="Synthetic homework", subject="math", created_by=self.parent,
            assigned_to=self.child, due_date=timezone.localdate() + timedelta(days=1),
        )
        self.post(f"/api/homework/{assignment.pk}/submit/", expected=400)
        self.assertFalse(UsageEvent.objects.exists())
        submission = self.post(f"/api/homework/{assignment.pk}/submit/", {
            "proof_url": "https://example.com/synthetic-proof", "notes": "Private synthetic prose",
        })
        self.client.force_authenticate(self.parent)
        self.post(f"/api/homework-submissions/{submission.data['id']}/approve/", expected=200)
        self.post(f"/api/homework-submissions/{submission.data['id']}/approve/", expected=200)
        self.assertEqual(UsageEvent.objects.count(), 2)
        self.assertEqual(self.event("homework", "submitted").source_id, submission.data["id"])
        self.assertEqual(self.event("homework", "approved").actor_id, self.parent.pk)
        self.assertNotIn("Private synthetic prose", str(list(UsageEvent.objects.values())))
        self.assertNotIn("synthetic-proof", str(list(UsageEvent.objects.values())))

    def test_project_noop_and_replayed_transitions_do_not_count_twice(self):
        project = Project.objects.create(
            title="Synthetic project", created_by=self.parent,
            assigned_to=self.child, status="in_review",
        )
        self.post(f"/api/projects/{project.pk}/submit/", expected=200)
        self.assertFalse(UsageEvent.objects.exists())
        project.status = "in_progress"
        project.save()
        self.post(f"/api/projects/{project.pk}/submit/", expected=200)
        self.post(f"/api/projects/{project.pk}/submit/", expected=200)
        self.client.force_authenticate(self.parent)
        self.post(f"/api/projects/{project.pk}/approve/", expected=200)
        self.post(f"/api/projects/{project.pk}/approve/", expected=200)
        self.assertEqual(UsageEvent.objects.count(), 2)
        self.assertEqual(self.event("projects", "submitted").actor_id, self.child.pk)
        self.assertEqual(self.event("projects", "approved").actor_id, self.parent.pk)

    def test_project_timer_records_only_successful_positive_human_clock_out(self):
        project = self.project()
        # Keep quiet-hour admission deterministic without changing clock-out time.
        with patch.object(ClockService, "QUIET_HOURS_START", 24), patch.object(ClockService, "QUIET_HOURS_END", 0):
            response = self.post("/api/clock/", {"action": "in", "project_id": project.pk})
        self.assertFalse(UsageEvent.objects.exists())
        entry_id = response.data["id"]
        TimeEntry.objects.filter(pk=entry_id).update(clock_in=timezone.now() - timedelta(minutes=20))
        self.post("/api/clock/", {"action": "out", "notes": "Private synthetic work notes"}, expected=200)
        self.post("/api/clock/", {"action": "out"}, expected=400)
        self.assertEqual(self.client.get("/api/clock/").status_code, 200)
        event = self.event("projects", "completed")
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual((event.actor_id, event.source, event.source_id), (self.child.pk, "timecards.timeentry", entry_id))
        self.assertNotIn("Private synthetic work notes", str(list(UsageEvent.objects.values())))

    def test_zero_minute_and_historical_homework_clock_outs_are_not_project_activity(self):
        TimeEntry.objects.create(user=self.child, project=self.project(), clock_in=timezone.now())
        self.post("/api/clock/", {"action": "out"}, expected=200)
        TimeEntry.objects.create(
            user=self.child, project=self.project(is_homework_plan=True),
            clock_in=timezone.now() - timedelta(minutes=20),
        )
        self.post("/api/clock/", {"action": "out"}, expected=200)
        self.assertEqual(TimeEntry.objects.filter(status="completed").count(), 2)
        self.assertFalse(UsageEvent.objects.exists())

    def test_automatic_and_shared_service_clock_outs_do_not_invent_human_activity(self):
        project = self.project()
        stale = TimeEntry.objects.create(
            user=self.child, project=project, clock_in=timezone.now() - timedelta(hours=9),
        )
        self.assertEqual(ClockService.auto_clock_out(), 1)
        stale.refresh_from_db()
        self.assertTrue(stale.auto_clocked_out)
        TimeEntry.objects.create(
            user=self.child, project=project, clock_in=timezone.now() - timedelta(minutes=20),
        )
        ClockService.clock_out(self.child)
        self.assertFalse(UsageEvent.objects.exists())

    def test_timecard_human_review_records_actual_parent_once(self):
        timecard = self.timecard()
        self.post(f"/api/timecards/{timecard.pk}/approve/", expected=403)
        self.client.force_authenticate(self.other_parent)
        self.post(f"/api/timecards/{timecard.pk}/approve/", expected=404)
        self.client.force_authenticate(self.parent)
        self.post(f"/api/timecards/{timecard.pk}/approve/", {"notes": "Private synthetic review"}, expected=200)
        self.client.force_authenticate(self.coparent)
        self.post(f"/api/timecards/{timecard.pk}/approve/", expected=200)
        event = self.event("projects", "approved")
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual((event.actor_id, event.source, event.source_id), (self.parent.pk, "timecards.timecard", timecard.pk))
        self.assertNotIn("Private synthetic review", str(list(UsageEvent.objects.values())))

    def test_timecard_api_retry_of_service_approval_creates_no_human_activity(self):
        timecard = self.timecard()
        TimecardService.approve_timecard(timecard, self.parent)
        self.client.force_authenticate(self.parent)
        self.post(f"/api/timecards/{timecard.pk}/approve/", expected=200)
        self.assertFalse(UsageEvent.objects.exists())

    def test_reading_records_actual_parent_actor_and_skips_retry_and_corrections(self):
        self.client.force_authenticate(self.parent)
        payload = {
            "book": self.book().pk, "duration_minutes": 2,
            "client_request_id": str(uuid4()), "user_id": self.child.pk,
        }
        response = self.post("/api/reading-sessions/", payload)
        self.post("/api/reading-sessions/", payload, expected=200)
        updated = self.client.patch(
            f"/api/reading-sessions/{response.data['id']}/", {"duration_minutes": 3}, format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(self.client.get("/api/reading-sessions/").status_code, 200)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(self.event("reading", "completed").actor_id, self.parent.pk)

    def test_reading_foreign_target_failure_creates_no_event(self):
        self.client.force_authenticate(self.other_parent)
        self.post("/api/reading-sessions/", {
            "book": self.book().pk, "user_id": self.child.pk,
            "duration_minutes": 2, "client_request_id": str(uuid4()),
        }, expected=404)
        self.assertFalse(ReadingSession.objects.exists())
        self.assertFalse(UsageEvent.objects.exists())

    def test_movement_records_parent_actor_and_deduplicates_uuid_replays(self):
        self.client.force_authenticate(self.parent)
        payload = {
            "movement_type_id": self.movement_type().pk,
            "duration_minutes": 2, "client_request_id": str(uuid4()),
            "user_id": self.child.pk,
        }
        self.post("/api/movement-sessions/", payload)
        self.post("/api/movement-sessions/", payload)
        self.post("/api/movement-sessions/", {**payload, "duration_minutes": 3}, expected=400)
        self.assertEqual(MovementSession.objects.count(), 1)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(self.event("movement", "completed").actor_id, self.parent.pk)

    def test_movement_api_retry_of_service_created_session_creates_no_event(self):
        movement_type = self.movement_type()
        request_id = uuid4()
        MovementSessionService.log_session(
            self.child, movement_type=movement_type,
            duration_minutes=2, client_request_id=request_id,
        )
        self.post("/api/movement-sessions/", {
            "movement_type_id": movement_type.pk, "duration_minutes": 2,
            "client_request_id": str(request_id),
        })
        self.assertFalse(UsageEvent.objects.exists())

    def test_habit_positive_and_negative_taps_have_distinct_saved_sources(self):
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Synthetic ritual",
            habit_type="both", xp_reward=0, max_taps_per_day=1,
        )
        self.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, expected=200)
        self.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, expected=400)
        self.post(f"/api/habits/{habit.pk}/log/", {"direction": -1}, expected=200)
        self.post(f"/api/habits/{habit.pk}/log/", {"direction": 0}, expected=400)
        self.assertEqual(UsageEvent.objects.count(), 2)
        self.assertNotEqual(
            self.event("habits", "completed").source_id,
            self.event("habits", "checked_in").source_id,
        )
        self.assertSetEqual(
            set(UsageEvent.objects.values_list("source_id", flat=True)),
            set(HabitLog.objects.values_list("pk", flat=True)),
        )

    def test_habit_shared_service_does_not_count_as_api_usage(self):
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Synthetic ritual", xp_reward=0,
        )
        HabitService.log_tap(self.child, habit, 1)
        self.assertFalse(UsageEvent.objects.exists())

    def test_reward_requests_count_separately_from_manual_approval(self):
        reward = Reward.objects.create(family=self.family, name="Synthetic reward", cost_coins=2)
        self.post(f"/api/rewards/{reward.pk}/redeem/", expected=400)
        self.assertFalse(UsageEvent.objects.exists())
        CoinService.award_coins(self.child, 2, "adjustment", description="Synthetic fixture")
        redemption = self.post(f"/api/rewards/{reward.pk}/redeem/")
        self.client.force_authenticate(self.parent)
        self.post(f"/api/redemptions/{redemption.data['id']}/approve/", expected=200)
        self.post(f"/api/redemptions/{redemption.data['id']}/approve/", expected=200)
        self.assertEqual(UsageEvent.objects.count(), 2)
        self.assertEqual(self.event("rewards", "requested").actor_id, self.child.pk)
        self.assertEqual(self.event("rewards", "approved").actor_id, self.parent.pk)

    def test_automatic_reward_approval_is_only_a_human_request(self):
        reward = Reward.objects.create(
            family=self.family, name="Synthetic instant reward", cost_coins=0,
            requires_parent_approval=False,
        )
        redemption = self.post(f"/api/rewards/{reward.pk}/redeem/")
        self.client.force_authenticate(self.parent)
        self.post(f"/api/redemptions/{redemption.data['id']}/approve/", expected=200)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(self.event("rewards", "requested").actor_id, self.child.pk)

    def test_reward_shared_service_does_not_count_as_api_usage(self):
        reward = Reward.objects.create(family=self.family, name="Synthetic reward", cost_coins=0)
        redemption = RewardService.request_redemption(self.child, reward)
        RewardService.approve(redemption, self.parent)
        self.assertFalse(UsageEvent.objects.exists())

    def test_designated_live_fixture_actions_are_excluded(self):
        LiveTestFamily.objects.create(
            namespace="usage-test", family=self.family, parent=self.parent, child=self.child,
        )
        self.post("/api/reading-sessions/", {
            "book": self.book().pk, "duration_minutes": 2, "client_request_id": str(uuid4()),
        })
        self.assertTrue(ReadingSession.objects.exists())
        self.assertFalse(UsageEvent.objects.exists())

    def test_telemetry_database_failure_does_not_undo_successful_activity(self):
        movement_type = self.movement_type()
        with patch("apps.usage.services.UsageEvent.objects.get_or_create", side_effect=DatabaseError("Synthetic failure")):
            self.post("/api/movement-sessions/", {
                "movement_type_id": movement_type.pk, "duration_minutes": 2,
            })
        self.assertEqual(MovementSession.objects.count(), 1)
        self.assertFalse(UsageEvent.objects.exists())
