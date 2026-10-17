"""Parent Today projects household work without journal or reflection bodies."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import override as timezone_override
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.projects.models import Project, User
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.timecards.models import Timecard, TimeEntry
from config.tests.factories import make_family


class ParentFamilyOverviewTests(TestCase):
    now = datetime(2026, 10, 17, 18, tzinfo=dt_timezone.utc)
    today = date(2026, 10, 17)

    def setUp(self):
        household = make_family(
            parents=[{"username": "overview-parent"}],
            children=[{"username": "abby", "display_name": "Abby", "hourly_rate": "10.00"},
                      {"username": "ben", "display_name": "Ben"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def overview(self, now=None):
        with patch("django.utils.timezone.now", return_value=now or self.now):
            return self.client.get("/api/dashboard/").json()["family_overview"]

    def homework(self, title="Schoolwork", **kwargs):
        return HomeworkAssignment.objects.create(
            title=title, subject="math", created_by=self.parent,
            assigned_to=kwargs.pop("assigned_to", self.child),
            due_date=kwargs.pop("due_date", self.today), **kwargs,
        )

    def submit_homework(self, assignment, status="pending", **kwargs):
        return HomeworkSubmission.objects.create(
            assignment=assignment, user=assignment.assigned_to,
            status=status, timeliness="on_time", **kwargs,
        )

    def chore(self, title="Chore", **kwargs):
        return Chore.objects.create(
            title=title, family=self.family, created_by=self.parent,
            assigned_to=kwargs.pop("assigned_to", self.child), **kwargs,
        )

    def complete_chore(self, chore, status="pending", **kwargs):
        return ChoreCompletion.objects.create(
            chore=chore, user=kwargs.pop("user", self.child), status=status,
            completed_date=kwargs.pop("completed_date", self.today),
            reward_amount_snapshot="0.00", coin_reward_snapshot=0, **kwargs,
        )

    def goal(self, **kwargs):
        child = kwargs.pop("user", self.child)
        goal = ChallengeGoal.objects.create(
            user=child, family=kwargs.pop("family", self.family), created_by=self.parent,
            name="Read together", metric="minutes", target=Decimal("20"), unit="minutes",
            timezone_name="America/Phoenix", starts_at=self.now - timedelta(days=1),
            ends_at=self.now + timedelta(days=1), is_catalog=kwargs.pop("is_catalog", False),
        )
        return ChallengeOccurrence.objects.create(
            goal=goal, starts_at=kwargs.pop("starts_at", goal.starts_at),
            ends_at=kwargs.pop("ends_at", goal.ends_at),
            snapshot={"name": "Read together", "target": "20.000", "unit": "minutes"},
            progress=Decimal("7.500"), **kwargs,
        )

    def test_parent_payload_contains_every_active_child_even_without_clocked_work(self):
        overview = self.overview()
        self.assertEqual(overview["date"], "2026-10-17")
        self.assertEqual(overview["timezone"], "America/Phoenix")
        self.assertEqual([row["name"] for row in overview["children"]], ["Abby", "Ben"])
        self.assertEqual(overview["children"][0]["clocked_week"], {"hours": 0, "earnings": 0})

    def test_disputed_timecards_are_actionable_and_family_scoped(self):
        other = make_family("Other", children=[{"username": "else-card-child"}])
        for child in (self.child, other.children[0]):
            Timecard.objects.create(user=child, week_start=self.today - timedelta(days=5),
                                    week_end=self.today + timedelta(days=1), status="disputed")
        response = self.client.get("/api/dashboard/").json()
        self.assertEqual(response.get("disputed_timecards"), 1)

    def test_homework_counts_actionable_work_separately_from_parent_review(self):
        self.homework("Due today")
        self.homework("Late", due_date=self.today - timedelta(days=2))
        self.submit_homework(self.homework("Waiting", due_date=self.today - timedelta(days=1)))
        self.submit_homework(self.homework("Done"), status="approved", decided_at=self.now)
        self.submit_homework(self.homework("Try again"), status="rejected")
        self.homework("Inactive", is_active=False)
        self.homework("Future", due_date=self.today + timedelta(days=1))
        self.assertEqual(self.overview()["children"][0]["homework"], {
            "due_today": 2, "overdue": 1, "pending_review": 1,
        })

    def test_chore_status_respects_periods_shared_chores_off_weeks_and_old_one_time_work(self):
        self.chore("Remaining")
        self.chore("Shared", assigned_to=None)
        self.complete_chore(self.chore("Pending"))
        self.complete_chore(self.chore("Weekly", recurrence="weekly"), status="approved",
                            completed_date=self.today - timedelta(days=self.today.weekday()))
        self.complete_chore(self.chore("Redo"), status="rejected")
        self.complete_chore(self.chore("Old daily"), status="approved",
                            completed_date=self.today - timedelta(days=1))
        self.complete_chore(self.chore("Finished once", recurrence="one_time"), status="approved",
                            completed_date=self.today - timedelta(days=5))
        self.complete_chore(self.chore("Once pending", recurrence="one_time"),
                            completed_date=self.today - timedelta(days=3))
        self.chore("Off week", week_schedule="alternating",
                   schedule_start_date=self.today - timedelta(days=7))
        self.chore("Unpublished", pending_parent_review=True)
        self.chore("Inactive", is_active=False)
        rows = self.overview()["children"]
        self.assertEqual(rows[0]["chores"], {"remaining": 4, "pending_review": 2, "approved": 1, "total": 7})
        self.assertEqual(rows[1]["chores"], {"remaining": 1, "pending_review": 0, "approved": 0, "total": 1})

    def test_parent_goals_are_current_frozen_scoped_and_capped(self):
        active = [self.goal() for _ in range(4)]
        self.goal(is_catalog=True)
        self.goal(status="completed", completed_at=self.now)
        self.goal(ends_at=self.now)
        self.goal(starts_at=self.now + timedelta(hours=1))
        goals = self.overview()["children"][0]["parent_goals"]
        self.assertEqual(goals["active_count"], 4)
        self.assertEqual(len(goals["items"]), 3)
        self.assertEqual(goals["items"][0], {
            "id": f"goal:{active[0].pk}", "name": "Read together",
            "progress": "7.500", "target": "20.000", "unit": "minutes",
            "ends_at": active[0].ends_at.isoformat(),
        })

    def test_weekly_parent_goal_has_current_zero_progress_before_a_child_opens_challenges(self):
        from apps.projects.parent_overview import build_family_overview
        old = self.goal()
        old.goal.starts_at = datetime(2026, 10, 5, 7, tzinfo=dt_timezone.utc)
        old.goal.ends_at = datetime(2026, 10, 12, 7, tzinfo=dt_timezone.utc)
        old.goal.repeat_weekly = True
        old.goal.save(update_fields=["starts_at", "ends_at", "repeat_weekly"])
        old.starts_at, old.ends_at = old.goal.starts_at, old.goal.ends_at
        old.status, old.completed_at = "completed", old.ends_at - timedelta(days=1)
        old.save(update_fields=["starts_at", "ends_at", "status", "completed_at"])
        with patch("django.utils.timezone.now", return_value=self.now):
            with CaptureQueriesContext(connection) as captured:
                summary = build_family_overview(self.parent)["children"][0]["parent_goals"]
        self.assertEqual(summary["active_count"], 1)
        self.assertEqual(summary["items"][0]["name"], "Read together")
        self.assertEqual(summary["items"][0]["progress"], "0")
        self.assertEqual(summary["items"][0]["ends_at"], "2026-10-19T07:00:00+00:00")
        self.assertTrue(summary["items"][0]["preview"])
        self.assertEqual(ChallengeOccurrence.objects.filter(goal=old.goal).count(), 1)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in captured))

    def test_completed_current_week_never_rearms_a_recurring_parent_goal(self):
        occurrence = self.goal(status="completed", completed_at=self.now)
        occurrence.goal.repeat_weekly = True
        occurrence.goal.save(update_fields=["repeat_weekly"])
        self.assertEqual(self.overview()["children"][0]["parent_goals"], {"active_count": 0, "items": []})

    def test_weekly_previews_keep_an_exact_total_and_use_the_saved_goal_timezone(self):
        from apps.projects.parent_overview import build_family_overview
        for _ in range(4):
            old = self.goal()
            old.goal.starts_at = datetime(2026, 10, 5, 7, tzinfo=dt_timezone.utc)
            old.goal.ends_at = datetime(2026, 10, 12, 7, tzinfo=dt_timezone.utc)
            old.goal.repeat_weekly = True
            old.goal.timezone_name = "Asia/Tokyo"
            old.goal.save(update_fields=["starts_at", "ends_at", "repeat_weekly", "timezone_name"])
            old.starts_at, old.ends_at = old.goal.starts_at, old.goal.ends_at
            old.save(update_fields=["starts_at", "ends_at"])
        # Tokyo has started Monday while the family's Phoenix clock is Sunday.
        now = datetime(2026, 10, 19, 2, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            summary = build_family_overview(self.parent)["children"][0]["parent_goals"]
        self.assertEqual(summary["active_count"], 4)
        self.assertEqual(len(summary["items"]), 3)
        self.assertTrue(all(item["preview"] for item in summary["items"]))
        self.assertEqual({item["ends_at"] for item in summary["items"]}, {"2026-10-25T15:00:00+00:00"})
        self.assertTrue(all(item["id"].endswith(":2026-10-19") for item in summary["items"]))

    def test_accomplishment_uses_only_confirmed_body_free_sources(self):
        self.submit_homework(self.homework("Math done"), status="approved", decided_at=self.now - timedelta(hours=1),
                             notes="PRIVATE SUBMISSION BODY")
        self.submit_homework(self.homework("Not approved"), notes="PRIVATE PENDING BODY")
        badge = Badge.objects.create(name="Steady learner", criteria_type="homework_count")
        award = UserBadge.objects.create(user=self.child, badge=badge)
        UserBadge.objects.filter(pk=award.pk).update(earned_at=self.now - timedelta(minutes=1))
        row = self.overview()["children"][0]
        self.assertEqual(row["recent_accomplishment"], {
            "kind": "badge", "title": "Steady learner",
            "occurred_at": (self.now - timedelta(minutes=1)).isoformat(),
        })
        self.assertNotIn("PRIVATE", str(row))
        self.assertIsNone(self.overview()["children"][1]["recent_accomplishment"])

    def test_latest_approved_work_or_completed_goal_is_featured_but_future_badges_are_not(self):
        self.submit_homework(self.homework("Homework success"), status="approved",
                             decided_at=self.now - timedelta(hours=3))
        self.assertEqual(self.overview()["children"][0]["recent_accomplishment"]["kind"], "homework")
        self.complete_chore(self.chore("Chore success"), status="approved",
                            decided_at=self.now - timedelta(hours=2))
        self.assertEqual(self.overview()["children"][0]["recent_accomplishment"]["title"], "Chore success")
        self.goal(status="completed", completed_at=self.now - timedelta(hours=1))
        badge = Badge.objects.create(name="Future badge", criteria_type="homework_count")
        award = UserBadge.objects.create(user=self.child, badge=badge)
        UserBadge.objects.filter(pk=award.pk).update(earned_at=self.now + timedelta(minutes=1))
        self.assertEqual(self.overview()["children"][0]["recent_accomplishment"]["kind"], "goal")

    def test_projection_never_reads_private_journal_or_reflection_tables(self):
        from apps.projects.parent_overview import build_family_overview
        with CaptureQueriesContext(connection) as captured:
            build_family_overview(self.parent)
        sql = " ".join(query["sql"] for query in captured).lower()
        self.assertNotIn("chronicle_", sql)
        self.assertNotIn("wellbeing_", sql)
        self.assertNotIn('"homework_homeworksubmission"."notes"', sql)

    def test_family_date_and_week_use_household_timezone_not_server_or_phone_date(self):
        # UTC Monday is still Sunday in Phoenix, so Sunday's homework is due
        # today and its completed work remains inside this household's week.
        now = datetime(2026, 10, 19, 2, tzinfo=dt_timezone.utc)
        self.homework("Sunday", due_date=date(2026, 10, 18))
        project = Project.objects.create(title="Weekend build", assigned_to=self.child, created_by=self.parent)
        TimeEntry.objects.create(user=self.child, project=project, status="completed",
                                 clock_in=now - timedelta(hours=1), clock_out=now)
        with timezone_override("UTC"):
            overview = self.overview(now)
        self.assertEqual(overview["date"], "2026-10-18")
        self.assertEqual(overview["children"][0]["homework"]["due_today"], 1)
        self.assertEqual(overview["children"][0]["clocked_week"], {"hours": 1, "earnings": 10})

    def test_no_cross_family_inactive_or_parent_rows_and_child_has_no_family_projection(self):
        other = make_family("Other", parents=[{"username": "else-parent"}],
                            children=[{"username": "else-child"}])
        self.homework("FOREIGN HOMEWORK", assigned_to=other.children[0])
        self.goal(user=other.children[0], family=other.family)
        # A mismatched legacy family FK must not leak a goal into this family.
        self.goal(family=other.family)
        self.sibling.is_active = False
        self.sibling.save(update_fields=["is_active"])
        overview = self.overview()
        self.assertEqual([row["kid_id"] for row in overview["children"]], [self.child.pk])
        self.assertNotIn("FOREIGN", str(overview))
        self.assertEqual(overview["children"][0]["parent_goals"]["active_count"], 0)
        self.client.force_authenticate(self.child)
        self.assertNotIn("family_overview", self.client.get("/api/dashboard/").json())
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

    def test_projection_query_count_does_not_grow_with_children_or_work_items(self):
        from apps.projects.parent_overview import build_family_overview
        self.chore("Initial")
        with patch("django.utils.timezone.now", return_value=self.now):
            with self.assertNumQueries(11):
                build_family_overview(self.parent)
            for index in range(3):
                child = User.objects.create_user(username=f"extra-{index}", role="child", family=self.family)
                self.homework(assigned_to=child)
                self.goal(user=child)
                self.chore(assigned_to=child)
            with self.assertNumQueries(11):
                overview = build_family_overview(self.parent)
        self.assertEqual(len(overview["children"]), 5)
