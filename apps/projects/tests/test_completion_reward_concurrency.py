"""Project approvals must pay once across independent PostgreSQL requests."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.achievements.models import ProjectSkillTag, Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects import signals
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ProjectCompletionRewardConcurrencyTests(TransactionTestCase):
    def test_overlapping_parent_approvals_award_each_completion_reward_once(self):
        family = make_family(
            "Concurrent approvals",
            parents=[{"username": "approval-parent-a"}, {"username": "approval-parent-b"}],
            children=[{"username": "approval-child"}],
        )
        child = family.children[0]
        category = SkillCategory.objects.create(name="Concurrent project rewards")
        skill = Skill.objects.create(name="Project practice", category=category)
        SkillProgress.objects.create(user=child, skill=skill, unlocked=True)
        project = Project.objects.create(
            title="One birdhouse",
            created_by=family.parents[0],
            assigned_to=child,
            status="in_review",
            difficulty=2,
            bonus_amount=Decimal("10.00"),
        )
        ProjectSkillTag.objects.create(project=project, skill=skill, xp_weight=1)
        prior_status_read = Barrier(2)
        original_track = signals._track_previous_value

        def track_simultaneous_approvals(instance, sender, field, default=None):
            previous = original_track(instance, sender, field, default)
            if sender is Project and instance.pk == project.pk and field == "status":
                # Both requests observe the unapproved state before either
                # writes it. A transition-only guard then pays both callers.
                prior_status_read.wait(timeout=5)
            return previous

        def approve(parent):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                client = APIClient()
                client.force_authenticate(parent)
                response = client.post(f"/api/projects/{project.pk}/approve/", {}, format="json")
                return response.status_code, response.content
            finally:
                connection.close()

        with patch.object(signals, "_track_previous_value", track_simultaneous_approvals), patch(
            "apps.rpg.services.GameLoopService.on_task_completed",
        ) as game_loop, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(approve, parent) for parent in family.parents]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual([code for code, _body in results], [200, 200], results)
        payments = PaymentLedger.objects.filter(project=project, entry_type="project_bonus")
        coins = CoinLedger.objects.filter(user=child, reason=CoinLedger.Reason.PROJECT_BONUS)
        progress = SkillProgress.objects.get(user=child, skill=skill)
        # Check the actual effects together: a receipt alone would not prove
        # that both ledger halves, XP, and the game loop remained idempotent.
        self.assertEqual(
            (list(payments.values_list("amount", flat=True)),
             list(coins.values_list("amount", flat=True)),
             progress.xp_points, game_loop.call_count,
             Notification.objects.filter(user=child, notification_type="project_approved").count(),
             ActivityEvent.objects.filter(event_type="project.complete", target_id=project.pk).count()),
            ([Decimal("10.00")], [20], 100, 1, 1, 1),
        )
        project.refresh_from_db()
        self.assertEqual(project.status, "completed")
        self.assertIsNotNone(project.completed_at)
