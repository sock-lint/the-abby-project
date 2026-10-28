"""My space summaries distinguish self confirmations and actual hourly pay."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification, NotificationType
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import Project
from apps.timecards.models import TimeEntry
from apps.timecards.services import TimecardService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PersonalDashboardCashAndConfirmationTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Dashboard summaries", parents=[{"username": "parent", "hourly_rate": "8.00"},
                                            {"username": "coparent"}],
            children=[{"username": "child", "hourly_rate": "8.00"}],
        )
        self.parent, self.coparent = family.parents
        self.child = family.children[0]
        self.client.force_authenticate(self.parent)

    def personal(self, method, path, data=None):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_ABBY_SPACE="personal")

    def dashboard(self, owner, *, personal=True):
        owner.refresh_from_db()
        self.client.force_authenticate(owner)
        response = self.personal("get", "/api/dashboard/") if personal else self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def complete_personal_chore(self):
        self.client.force_authenticate(self.parent)
        created = self.personal("post", "/api/chores/", {"title": "My tidy", "coin_reward": 3})
        self.assertEqual(created.status_code, 201, created.data)
        chore = Chore.objects.get(title="My tidy")
        completed = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(completed.status_code, 201, completed.data)
        self.assertEqual(completed.data["status"], "approved")
        return ChoreCompletion.objects.get(pk=completed.data["id"])

    def test_self_confirmed_chore_awards_coins_without_claiming_an_external_approval(self):
        self.assertIsNone(self.dashboard(self.parent)["since_last_visit"])
        completion = self.complete_personal_chore()
        self.assertEqual(completion.decided_by_id, self.parent.pk)
        self.assertEqual(completion.reward_amount_snapshot, 0)
        self.assertFalse(PaymentLedger.objects.exists())
        note = Notification.objects.get(user=self.parent, notification_type=NotificationType.CHORE_APPROVED)
        self.assertEqual(note.link, "/chores?space=personal")
        catchup = self.dashboard(self.parent)["since_last_visit"]
        self.assertGreaterEqual(catchup["coins_earned"], 3)
        self.assertEqual(catchup["approvals"], 0)

    def test_self_confirmation_does_not_hide_genuine_coparent_and_other_approval_notices(self):
        self.dashboard(self.parent)
        self.complete_personal_chore()
        chore = Chore.objects.create(family=self.parent.family, created_by=self.coparent,
                                     assigned_to=self.parent, title="Family-reviewed chore")
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.parent, completed_date=timezone.localdate(),
            reward_amount_snapshot=Decimal("2.50"), coin_reward_snapshot=0,
        )
        self.client.force_authenticate(self.coparent)
        approved = self.client.post(f"/api/chore-completions/{completion.pk}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(PaymentService.get_balance(self.parent), Decimal("2.50"))
        Notification.objects.create(user=self.parent, title="Saved exchange approval",
                                     notification_type=NotificationType.EXCHANGE_APPROVED)
        Notification.objects.create(user=self.child, title="Someone else's approval",
                                     notification_type=NotificationType.PROJECT_APPROVED)
        catchup = self.dashboard(self.parent)["since_last_visit"]
        self.assertEqual(catchup["approvals"], 2)
        self.assertEqual(PaymentService.get_balance(self.parent), Decimal("2.50"))

    def test_child_external_chore_approval_and_other_types_keep_their_counts(self):
        self.dashboard(self.child)
        chore = Chore.objects.create(family=self.child.family, assigned_to=self.child,
                                     created_by=self.parent, title="Child tidy", reward_amount=Decimal("5.00"))
        submitted = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self.assertEqual(submitted.data["status"], "pending")
        self.client.force_authenticate(self.parent)
        approved = self.client.post(f"/api/chore-completions/{submitted.data['id']}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        for kind in (NotificationType.HOMEWORK_APPROVED, NotificationType.CREATION_APPROVED,
                     NotificationType.EXCHANGE_APPROVED, NotificationType.TIMECARD_APPROVED,
                     NotificationType.PROJECT_APPROVED):
            Notification.objects.create(user=self.child, title="Saved approval notice", notification_type=kind)
        self.assertEqual(self.dashboard(self.child)["since_last_visit"]["approvals"], 6)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("5.00"))

    def test_genuine_coparent_project_approval_retains_its_count(self):
        self.dashboard(self.parent)
        project = Project.objects.create(title="Coparent-reviewed project", assigned_to=self.parent,
                                         created_by=self.parent, status="in_progress", hourly_rate_override=0)
        self.client.force_authenticate(self.coparent)
        approved = self.client.post(f"/api/projects/{project.pk}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        note = Notification.objects.get(user=self.parent, notification_type=NotificationType.PROJECT_APPROVED)
        self.assertEqual(note.link, f"/projects/{project.pk}?space=personal")
        self.assertEqual(self.dashboard(self.parent)["since_last_visit"]["approvals"], 1)

    def test_personal_clock_hours_project_zero_cash_matching_native_timecard(self):
        started = datetime(2026, 10, 28, 17, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=started):
            created = self.personal("post", "/api/projects/", {"title": "Personal quilt", "status": "active"})
            self.assertEqual(created.status_code, 201, created.data)
            project = Project.objects.get(pk=created.data["id"])
            self.assertEqual(project.hourly_rate_override, 0)
            clocked_in = self.personal("post", "/api/clock/", {"action": "in", "project_id": project.pk})
            self.assertEqual(clocked_in.status_code, 201, clocked_in.data)
        with patch("django.utils.timezone.now", return_value=started + timedelta(hours=2)):
            clocked_out = self.personal("post", "/api/clock/", {"action": "out"})
            self.assertEqual(clocked_out.status_code, 200, clocked_out.data)
            self.assertEqual(clocked_out.data["duration_minutes"], 120)
            card = TimecardService.generate_weekly_timecard(self.parent, started.date() - timedelta(days=started.weekday()))
            self.assertEqual((card.total_hours, card.hourly_earnings), (Decimal("2.00"), Decimal("0.00")))
            self.assertEqual(PaymentService.get_balance(self.parent), 0)
            before = list(PaymentLedger.objects.values())
            personal = self.dashboard(self.parent)["this_week"]
            self.assertEqual(personal["hours_worked"], 2.0)
            self.assertEqual(personal["projects_worked_on"], 1)
            with self.subTest(surface="personal_cash_projection"):
                self.assertEqual(personal["earnings"], 0.0)
            family = self.dashboard(self.parent, personal=False)["this_week"]
            self.assertEqual(family["earnings"], 16.0)
            self.assertEqual(list(PaymentLedger.objects.values()), before)

    def test_personal_cash_projection_keeps_saved_paid_family_work_and_cent_rounding(self):
        now = datetime(2026, 10, 28, 19, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            project = Project.objects.create(title="Existing paid work", assigned_to=self.parent,
                                             created_by=self.coparent, hourly_rate_override=Decimal("12.50"))
            TimeEntry.objects.create(user=self.parent, project=project, status="completed",
                                     clock_in=now - timedelta(minutes=68), clock_out=now)
            card = TimecardService.generate_weekly_timecard(self.parent, now.date() - timedelta(days=now.weekday()))
            self.assertEqual(card.hourly_earnings, Decimal("14.13"))
            before = list(PaymentLedger.objects.values())
            dashboard = self.dashboard(self.parent)
            self.assertEqual(dashboard["current_balance"], 14.13)
            self.assertEqual(dashboard["this_week"]["earnings"], 14.13)
            self.assertEqual(list(PaymentLedger.objects.values()), before)

    def test_child_hourly_dashboard_and_native_timecard_keep_cash_with_personal_hint(self):
        now = datetime(2026, 10, 28, 19, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            project = Project.objects.create(title="Child work", assigned_to=self.child, created_by=self.parent)
            TimeEntry.objects.create(user=self.child, project=project, status="completed",
                                     clock_in=now - timedelta(hours=2), clock_out=now)
            card = TimecardService.generate_weekly_timecard(self.child, now.date() - timedelta(days=now.weekday()))
            self.assertEqual(card.hourly_earnings, Decimal("16.00"))
            before = list(PaymentLedger.objects.values())
            dashboard = self.dashboard(self.child)
            self.assertEqual(dashboard["this_week"]["earnings"], 16.0)
            self.assertEqual(dashboard["current_balance"], 16.0)
            self.assertEqual(list(PaymentLedger.objects.values()), before)
