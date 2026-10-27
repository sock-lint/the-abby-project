"""Transferring personal work to a child restores the child's normal hourly pay."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ingestion.models import ProjectIngestionJob
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from apps.timecards.models import TimeEntry
from apps.timecards.services import TimecardService
from config.tests.base import BaseFamilyAPITestCase


class PersonalProjectRateTransferTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "rate-transfer-parent", "hourly_rate": "55.00"}]
    family_children = [{"username": "rate-transfer-child", "hourly_rate": "8.50"}]

    def setUp(self):
        self.parent, self.child = self.parents[0], self.children[0]
        self.client.force_authenticate(self.parent)
        today = timezone.localdate()
        self.monday = today - timedelta(days=today.weekday())

    def personal_project(self):
        response = self.client.post("/api/projects/", {
            "title": "Parent's own making", "bonus_amount": "40.00", "hourly_rate_override": "99.00",
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual((project.assigned_to_id, project.hourly_rate_override), (self.parent.pk, 0))
        return project

    def family_edit(self, project, **values):
        response = self.client.patch(f"/api/projects/{project.pk}/", values, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        return project

    def two_hour_card(self, project, user):
        start = timezone.make_aware(datetime.combine(self.monday, time(12)))
        TimeEntry.objects.create(
            user=user, project=project, status=TimeEntry.Status.COMPLETED,
            clock_in=start, clock_out=start + timedelta(hours=2),
        )
        return TimecardService.generate_weekly_timecard(user, self.monday)

    def assert_hourly_pay(self, card, user, amount):
        self.assertEqual(card.total_hours, Decimal("2.00"))
        self.assertEqual(card.hourly_earnings, Decimal(amount))
        self.assertEqual(card.total_earnings, Decimal(amount))
        self.assertEqual(list(PaymentLedger.objects.filter(
            timecard=card, user=user, entry_type="hourly",
        ).values_list("amount", flat=True)), [Decimal(amount)])
        repeated = TimecardService.generate_weekly_timecard(user, self.monday)
        self.assertEqual(repeated.pk, card.pk)
        self.assertEqual(PaymentLedger.objects.filter(timecard=card, entry_type="hourly").count(), 1)

    def test_personal_project_assignment_without_rate_restores_child_default_pay(self):
        project = self.personal_project()
        self.family_edit(project, assigned_to_id=self.child.pk)
        self.assert_hourly_pay(self.two_hour_card(project, self.child), self.child, "17.00")
        self.assertIsNone(project.hourly_rate_override)
        self.assertFalse(PaymentLedger.objects.filter(user=self.parent).exists())

    def test_personal_import_assignment_without_rate_restores_child_default_pay(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type="url", status="ready", result_json={"title": "Imported work"},
        )
        response = self.client.post(f"/api/projects/ingest/{job.pk}/commit/", {},
                                    format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual(project.hourly_rate_override, 0)
        self.family_edit(project, assigned_to_id=self.child.pk)
        self.assert_hourly_pay(self.two_hour_card(project, self.child), self.child, "17.00")

    def test_family_edit_form_null_rate_payload_uses_child_default_pay(self):
        project = self.personal_project()
        # The Family form clears an inherited parent-only zero when changing
        # the assignee, unless the user explicitly edits the override.
        self.family_edit(project, title=project.title, assigned_to_id=str(self.child.pk),
                         payment_kind="required", bonus_amount="0", hourly_rate_override=None)
        self.assert_hourly_pay(self.two_hour_card(project, self.child), self.child, "17.00")

    def test_explicit_zero_on_child_transfer_remains_an_unpaid_project(self):
        project = self.personal_project()
        self.family_edit(project, assigned_to_id=self.child.pk, hourly_rate_override="0.00")
        self.assertEqual(project.hourly_rate_override, 0)
        self.assert_hourly_pay(self.two_hour_card(project, self.child), self.child, "0.00")

    def test_existing_child_zero_and_positive_parent_overrides_remain_explicit(self):
        child_project = Project.objects.create(
            title="Explicit unpaid child work", created_by=self.parent, assigned_to=self.child, hourly_rate_override=0,
        )
        self.family_edit(child_project, title="Still unpaid")
        self.assertEqual(child_project.hourly_rate_override, 0)
        project = self.personal_project()
        self.family_edit(project, hourly_rate_override="12.00")
        self.family_edit(project, assigned_to_id=self.child.pk)
        self.assertEqual(project.hourly_rate_override, Decimal("12.00"))
        self.assert_hourly_pay(self.two_hour_card(project, self.child), self.child, "24.00")

    def test_nonzero_parent_hourly_rate_still_cannot_pay_personal_work(self):
        project = self.personal_project()
        response = self.client.patch(f"/api/projects/{project.pk}/", {
            "description": "Keep my own project", "hourly_rate_override": "90.00", "bonus_amount": "20.00",
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 200, response.content)
        approved = self.client.post(f"/api/projects/{project.pk}/approve/", {},
                                    format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(approved.status_code, 200, approved.content)
        project.refresh_from_db()
        self.assertEqual((project.assigned_to_id, project.bonus_amount, project.hourly_rate_override), (self.parent.pk, 0, 0))
        # Test the native service too: public generation callers select children,
        # but the service itself must not fall back to this parent's $55 rate.
        self.assert_hourly_pay(self.two_hour_card(project, self.parent), self.parent, "0.00")
        self.assertFalse(PaymentLedger.objects.filter(user=self.parent).exclude(amount=0).exists())
