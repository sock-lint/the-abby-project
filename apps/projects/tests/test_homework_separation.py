"""Homework plans are study instructions, never a second paid project."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.homework.models import HomeworkAssignment
from apps.homework.services import HomeworkService
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.schemas import (
    ClockInIn, CompleteMilestoneIn, GetProjectIn, ListProjectsIn, ProjectActionIn,
    RequestProjectChangesIn, SaveProjectAsTemplateIn, UpdateProjectIn, UpdateProjectStatusIn,
)
from apps.mcp_server.tools import projects as project_tools, templates as template_tools
from apps.mcp_server.tools import timecards as timecard_tools
from apps.mcp_server.tools.dashboard import _build_user_dashboard
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectCompletionRewardReceipt, ProjectMilestone, ProjectStep
from apps.rewards.models import CoinLedger
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import ClockService, TimecardService
from config.tests.factories import make_family


class HomeworkProjectSeparationTests(TestCase):
    def setUp(self):
        # Tuesday noon in Phoenix keeps the one-hour entries inside the
        # requested week, including when CI runs just after Monday midnight.
        clock = patch("django.utils.timezone.now", return_value=datetime(
            2026, 10, 20, 19, tzinfo=datetime_timezone.utc,
        ))
        clock.start()
        self.addCleanup(clock.stop)
        self.house = make_family(parents=[{"username": "study-parent"}], children=[{
            "username": "study-child", "hourly_rate": Decimal("8.00"),
        }])
        self.parent, self.child = self.house.parents[0], self.house.children[0]
        self.plan = Project.objects.create(
            title="Science report plan", assigned_to=self.child, created_by=self.parent,
            status="in_progress", bonus_amount=Decimal("20.00"),
        )
        # Deliberately use the legacy shape: no durable marker was present.
        self.assignment = HomeworkAssignment.objects.create(
            title="Science report", subject="science", assigned_to=self.child,
            created_by=self.parent, due_date=timezone.localdate() + timedelta(days=7),
            project=self.plan,
        )
        self.work = Project.objects.create(
            title="Build a birdhouse", assigned_to=self.child, created_by=self.parent,
            status="in_progress",
        )
        self.client = APIClient()

    def entry(self, project, *, status="completed"):
        now = timezone.now()
        return TimeEntry.objects.create(
            user=self.child, project=project, status=status,
            clock_in=now - timedelta(hours=1),
            clock_out=now if status == "completed" else None,
        )

    @patch("apps.timecards.services.timezone.localtime")
    def test_linked_homework_rejects_clock_in_in_service_and_rest(self, localtime):
        localtime.return_value = timezone.now().replace(hour=12)
        with self.assertRaisesRegex(ValueError, "[Hh]omework"):
            ClockService.clock_in(self.child, self.plan)
        self.client.force_authenticate(self.child)
        response = self.client.post("/api/clock/", {"action": "in", "project_id": self.plan.pk})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TimeEntry.objects.exists())

    @patch("apps.rpg.services.safe_game_loop_call")
    @patch("apps.achievements.services.AwardService.grant")
    def test_legacy_active_homework_can_clock_out_without_work_rewards(self, grant, game_loop):
        entry = self.entry(self.plan, status="active")
        result = ClockService.clock_out(self.child)
        self.assertEqual(result.pk, entry.pk)
        self.assertEqual(result.status, "completed")
        grant.assert_not_called()
        game_loop.assert_not_called()

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_project_and_milestone_completion_do_not_reward_homework(self, game_loop):
        milestone = ProjectMilestone.objects.create(
            project=self.plan, title="Research", bonus_amount=Decimal("4.00"),
        )
        milestone.is_completed = True
        milestone.save()
        milestone.refresh_from_db()
        self.assertIsNotNone(milestone.completed_at)
        self.plan.status = "completed"
        self.plan.save()
        self.assertFalse(PaymentLedger.objects.filter(project=self.plan).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(ProjectCompletionRewardReceipt.objects.filter(project=self.plan).exists())
        game_loop.assert_not_called()

    def test_weekly_timecard_excludes_legacy_homework_hours_and_bonus(self):
        self.entry(self.plan)
        self.entry(self.work)
        Project.objects.filter(pk=self.plan.pk).update(status="completed", completed_at=timezone.now())
        today = timezone.localdate()
        card = TimecardService.generate_weekly_timecard(self.child, today - timedelta(days=today.weekday()))
        self.assertEqual(card.total_hours, Decimal("1.00"))
        self.assertEqual(card.hourly_earnings, Decimal("8.00"))
        self.assertEqual(card.bonus_earnings, Decimal("0.00"))
        self.assertFalse(PaymentLedger.objects.filter(project=self.plan).exists())

    def test_project_lists_and_dashboard_exclude_homework_but_detail_keeps_steps(self):
        step = ProjectStep.objects.create(project=self.plan, title="Read the sources")
        for user in (self.parent, self.child):
            self.client.force_authenticate(user)
            listing = self.client.get("/api/projects/").json()["results"]
            self.assertEqual([row["id"] for row in listing], [self.work.pk])
        detail = self.client.get(f"/api/projects/{self.plan.pk}/").json()
        self.assertTrue(detail["is_homework_plan"])
        self.assertEqual(detail["homework_assignment_id"], self.assignment.pk)
        self.assertEqual(detail["steps"][0]["id"], step.pk)
        response = self.client.post(f"/api/projects/{self.plan.pk}/steps/{step.pk}/complete/")
        self.assertEqual(response.status_code, 200)
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual([row["id"] for row in dashboard["active_projects"]], [self.work.pk])

    def test_homework_cannot_be_reassigned_or_given_project_pay(self):
        self.client.force_authenticate(self.parent)
        for field, value in (("bonus_amount", "50.00"), ("hourly_rate_override", "10.00"),
                             ("payment_kind", "bounty"), ("assigned_to_id", None)):
            with self.subTest(field=field):
                response = self.client.patch(f"/api/projects/{self.plan.pk}/", {field: value}, format="json")
                self.assertEqual(response.status_code, 400)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.assigned_to, self.child)

    def test_durable_marker_keeps_deleted_assignments_out_of_paid_work(self):
        self.plan.is_homework_plan = True
        self.plan.save(update_fields=["is_homework_plan"])
        self.assignment.delete()
        self.plan.refresh_from_db()
        self.assertTrue(self.plan.is_homework)
        self.assertIsNone(self.plan.homework_assignment_id)
        self.assertFalse(Project.objects.work_projects().filter(pk=self.plan.pk).exists())
        with self.assertRaisesRegex(ValueError, "Homework"):
            ClockService.clock_in(self.child, self.plan)

    @patch("config.llm.complete_json", return_value={"title": "A study plan", "steps": [{"title": "Read"}]})
    @patch("apps.homework.ai_settings.planner_options", return_value={})
    def test_new_planner_marks_homework_before_linking(self, options, complete):
        assignment = HomeworkAssignment.objects.create(
            title="Book report", subject="reading", assigned_to=self.child,
            created_by=self.parent, due_date=self.assignment.due_date,
        )
        HomeworkService.plan_assignment(assignment, self.parent)
        self.assertTrue(assignment.project.is_homework_plan)
        self.assertEqual(assignment.project.steps.get().title, "Read")
        assignment.delete()
        self.assertTrue(Project.objects.get(title="A study plan").is_homework)

    def test_unsettled_legacy_hourly_credits_are_reconciled_append_only(self):
        self.entry(self.plan)
        self.entry(self.work)
        today = timezone.localdate()
        week = today - timedelta(days=today.weekday())
        card = Timecard.objects.create(
            user=self.child, week_start=week, week_end=week + timedelta(days=6),
            total_hours=2, hourly_earnings=16, total_earnings=16,
        )
        original = PaymentLedger.objects.create(
            user=self.child, timecard=card, project=self.plan, amount=8, entry_type="hourly",
        )
        PaymentLedger.objects.create(
            user=self.child, timecard=card, project=self.work, amount=8, entry_type="hourly",
        )
        updated = TimecardService.generate_weekly_timecard(self.child, week)
        self.assertEqual(updated.total_earnings, Decimal("8.00"))
        self.assertTrue(PaymentLedger.objects.filter(pk=original.pk, amount=8).exists())
        self.assertEqual(list(PaymentLedger.objects.filter(project=self.plan).order_by("pk").values_list("amount", flat=True)),
                         [Decimal("8.00"), Decimal("-8.00")])
        TimecardService.generate_weekly_timecard(self.child, week)
        self.assertEqual(PaymentLedger.objects.filter(timecard=card).count(), 3)

    def test_approved_paid_and_closed_history_stays_immutable(self):
        today = timezone.localdate()
        week = today - timedelta(days=today.weekday())
        card = Timecard.objects.create(
            user=self.child, week_start=week, week_end=week + timedelta(days=6),
            total_hours=2, hourly_earnings=16, total_earnings=16,
        )
        PaymentLedger.objects.create(
            user=self.child, timecard=card, project=self.plan, amount=16, entry_type="hourly",
        )
        for status in ("approved", "paid", "closed"):
            card.status = status
            card.save(update_fields=["status"])
            result = TimecardService.generate_weekly_timecard(self.child, week)
            self.assertEqual(result.total_earnings, 16)
            self.assertEqual(result.status, status)
            self.assertEqual(PaymentLedger.objects.filter(timecard=card).count(), 1)

    def test_dashboard_earnings_and_work_streaks_ignore_historical_homework_entries(self):
        self.entry(self.plan)
        self.client.force_authenticate(self.child)
        child = self.client.get("/api/dashboard/").json()
        self.assertEqual(child["this_week"]["hours_worked"], 0)
        self.assertEqual(child["this_week"]["earnings"], 0)
        self.assertEqual(child["streak_days"], 0)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/dashboard/").json()["this_week_by_kid"], [])
        mcp = _build_user_dashboard(self.child)
        self.assertEqual(mcp["hours_this_week"], 0)
        self.assertEqual([row["id"] for row in mcp["active_projects"]], [self.work.pk])

    def test_homework_uses_homework_submission_instead_of_project_lifecycle(self):
        for user, actions in ((self.parent, ("approve", "activate", "request-changes")),
                              (self.child, ("submit",))):
            self.client.force_authenticate(user)
            for action in actions:
                with self.subTest(action=action):
                    response = self.client.post(f"/api/projects/{self.plan.pk}/{action}/")
                    self.assertEqual(response.status_code, 400)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "in_progress")

    def test_mcp_keeps_detail_but_blocks_work_lifecycle_clock_and_template_routes(self):
        with override_user(self.parent):
            listed = project_tools.list_projects(ListProjectsIn())
            self.assertEqual([row["id"] for row in listed["projects"]], [self.work.pk])
            self.assertTrue(project_tools.get_project(GetProjectIn(project_id=self.plan.pk))["is_homework_plan"])
            for fn, params in (
                (project_tools.update_project_status, UpdateProjectStatusIn(project_id=self.plan.pk, status="completed")),
                (project_tools.approve_project, ProjectActionIn(project_id=self.plan.pk)),
                (project_tools.activate_project, ProjectActionIn(project_id=self.plan.pk)),
                (project_tools.request_project_changes, RequestProjectChangesIn(project_id=self.plan.pk)),
                (project_tools.update_project, UpdateProjectIn(project_id=self.plan.pk, bonus_amount=Decimal("50.00"))),
                (template_tools.save_project_as_template, SaveProjectAsTemplateIn(project_id=self.plan.pk)),
            ):
                with self.subTest(tool=fn.__name__), self.assertRaises(MCPValidationError):
                    fn(params)
            with self.assertRaises(MCPValidationError):
                timecard_tools.clock_in(ClockInIn(project_id=self.plan.pk, user_id=self.child.pk))

    def test_mcp_homework_milestone_keeps_progress_without_rewarding_bonus(self):
        milestone = ProjectMilestone.objects.create(project=self.plan, title="Draft", bonus_amount=Decimal("15.00"))
        with override_user(self.parent):
            result = project_tools.complete_milestone(CompleteMilestoneIn(milestone_id=milestone.pk))
        self.assertTrue(result["milestone"]["is_completed"])
        self.assertEqual(result["coins_awarded"], 0)
        self.assertEqual(result["xp_awarded"], 0)
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

