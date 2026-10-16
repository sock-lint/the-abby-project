"""Exercise the completion-history migration without issuing historical rewards."""
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.activity.services import ActivityLogService
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectCompletionRewardReceipt
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class ProjectCompletionRewardBackfillTests(TestCase):
    def setUp(self):
        family = make_family(
            "Historical project rewards",
            parents=[{"username": "history-parent"}],
            children=[{"username": "history-child"}],
        )
        self.parent = family.parents[0]
        self.child = family.children[0]
        category = SkillCategory.objects.create(name="Existing project progress")
        skill = Skill.objects.create(name="Existing practice", category=category)
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=123, level=1)

    def project(self, title, **fields):
        return Project.objects.create(
            title=title, created_by=self.parent,
            **{"assigned_to": self.child, "status": "in_progress", "bonus_amount": "10.00", **fields},
        )

    def backfill(self):
        migration = import_module("apps.projects.migrations.0021_backfill_project_completion_receipts")
        # settings_test skips migrations. Call the real RunPython function
        # against its normal apps/schema-editor interface and current schema.
        migration.backfill_completion_receipts(apps, SimpleNamespace(connection=connection))

    def reward_state(self):
        return {
            "payments": list(PaymentLedger.objects.order_by("pk").values()),
            "coins": list(CoinLedger.objects.order_by("pk").values()),
            "progress": list(SkillProgress.objects.order_by("pk").values()),
            "notifications": list(Notification.objects.order_by("pk").values()),
            "activity": list(ActivityEvent.objects.order_by("pk").values()),
        }

    def completion_event(self, project, *, event_type="project.complete", **fields):
        return ActivityLogService.record(
            category="approval", event_type=event_type,
            summary="Synthetic historical completion", subject=self.child,
            target=project, **fields,
        )

    def test_backfill_claims_completed_reopened_and_independently_recorded_history(self):
        completed = self.project("Previously completed", status="completed")
        reopened = self.project("Reopened after completion", completed_at=timezone.now())
        paid = self.project("Only project-bonus ledger survived")
        bounty = self.project("Only bounty ledger survived", payment_kind="bounty")
        activity = self.project("Only completion activity survived")
        unassigned = self.project("Old unassigned completion", status="completed", assigned_to=None)
        for project, entry_type in ((paid, "project_bonus"), (bounty, "bounty_payout")):
            PaymentLedger.objects.create(
                project=project, user=self.child, amount="10.00", entry_type=entry_type,
            )
        self.completion_event(activity)
        CoinLedger.objects.create(user=self.child, amount=7, reason="adjustment")
        before = self.reward_state()

        self.backfill()

        self.assertEqual(
            set(ProjectCompletionRewardReceipt.objects.values_list("project_id", "user_id", "historical")),
            {(project.pk, project.assigned_to_id, True)
             for project in (completed, reopened, paid, bounty, activity, unassigned)},
        )
        self.assertEqual(self.reward_state(), before)

    def test_unrelated_work_and_wrong_content_types_do_not_claim_new_projects(self):
        fresh = self.project("Never completed")
        hourly = self.project("Only hourly work")
        milestone = self.project("Only milestone bonus")
        xp_only = self.project("Only timecard XP activity")
        wrong_type = self.project("Colliding foreign target id")
        wrong_event = self.project("Correct target but other event")
        for project, entry_type in ((hourly, "hourly"), (milestone, "milestone_bonus")):
            PaymentLedger.objects.create(
                project=project, user=self.child, amount="3.00", entry_type=entry_type,
            )
        self.completion_event(
            xp_only, event_type="award.xp", xp_delta=10, extras={"project_id": xp_only.pk},
        )
        event = self.completion_event(wrong_type)
        event.target_ct = ContentType.objects.get_for_model(User)
        event.save(update_fields=["target_ct"])
        self.completion_event(wrong_event, event_type="milestone.complete")
        before = self.reward_state()

        self.backfill()

        self.assertFalse(ProjectCompletionRewardReceipt.objects.filter(
            project__in=[fresh, hourly, milestone, xp_only, wrong_type, wrong_event],
        ).exists())
        self.assertEqual(self.reward_state(), before)

    def test_repeated_backfill_preserves_existing_live_receipt_and_its_recipient(self):
        project = self.project("Already protected live completion", status="completed")
        receipt = ProjectCompletionRewardReceipt.objects.create(
            project=project, user=self.parent, historical=False,
        )
        original = (receipt.pk, receipt.user_id, receipt.created_at, receipt.historical)

        self.backfill()
        self.backfill()

        receipt.refresh_from_db()
        self.assertEqual(
            (receipt.pk, receipt.user_id, receipt.created_at, receipt.historical), original,
        )
        self.assertEqual(ProjectCompletionRewardReceipt.objects.count(), 1)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_migrated_completion_cannot_pay_again_after_reopening(self, game_loop):
        project = self.project("Reapprove historical completion", status="completed")
        self.backfill()
        before = self.reward_state()

        project.status = "in_progress"
        project.bonus_amount = "999.00"
        project.save()
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post(f"/api/projects/{project.pk}/approve/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.reward_state(), before)
        game_loop.assert_not_called()
        project.refresh_from_db()
        self.assertEqual(project.status, "completed")
        self.assertTrue(ProjectCompletionRewardReceipt.objects.get(project=project).historical)

    def test_backfill_claims_every_project_across_batches_and_is_repeatable(self):
        Project.objects.bulk_create([
            Project(title=f"Archived completion {index}", status="completed",
                    created_by=self.parent, assigned_to=self.child)
            for index in range(503)
        ])

        self.backfill()
        first_receipts = list(ProjectCompletionRewardReceipt.objects.order_by("pk").values())
        self.backfill()

        self.assertEqual(len(first_receipts), 503)
        self.assertEqual(
            list(ProjectCompletionRewardReceipt.objects.order_by("pk").values()), first_receipts,
        )
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(Notification.objects.exists())
