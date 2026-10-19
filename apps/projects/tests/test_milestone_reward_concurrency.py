"""Overlapping PostgreSQL completions must share one milestone reward."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, local
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.achievements.models import MilestoneSkillTag, Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import Project, ProjectMilestone
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MilestoneRewardConcurrencyTests(TransactionTestCase):
    def test_overlapping_completions_pay_xp_money_and_drop_once(self):
        family = make_family(
            "Concurrent milestone approvals",
            parents=[{"username": "milestone-parent-a"}, {"username": "milestone-parent-b"}],
            children=[{"username": "milestone-child"}],
        )
        child = family.children[0]
        category = SkillCategory.objects.create(name="Concurrent milestone skills")
        skill = Skill.objects.create(name="Wall building", category=category)
        SkillProgress.objects.create(user=child, skill=skill, unlocked=True)
        project = Project.objects.create(
            title="One set of walls", created_by=family.parents[0], assigned_to=child,
            status="in_progress",
        )
        milestone = ProjectMilestone.objects.create(
            project=project, title="Walls", bonus_amount=Decimal("5.00"),
        )
        MilestoneSkillTag.objects.create(milestone=milestone, skill=skill, xp_amount=23)
        from apps.achievements.services import _lock_award_user

        before_award_lock = Barrier(2)
        worker_state = local()

        def lock_simultaneous_completions(user):
            if not getattr(worker_state, "started", False):
                worker_state.started = True
                before_award_lock.wait(timeout=5)
            return _lock_award_user(user)

        def complete(parent):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                client = APIClient()
                client.force_authenticate(parent)
                response = client.post(
                    f"/api/projects/{project.pk}/milestones/{milestone.pk}/complete/", {}, format="json",
                )
                return response.status_code, response.content
            finally:
                connection.close()

        with patch("apps.achievements.services._lock_award_user", lock_simultaneous_completions), patch(
            "apps.rpg.services.GameLoopService.on_task_completed",
        ) as game_loop, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(complete, parent) for parent in family.parents]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual([code for code, _body in results], [200, 200], results)
        self.assertEqual(
            (list(PaymentLedger.objects.filter(project=project).values_list("amount", flat=True)),
             SkillProgress.objects.get(user=child, skill=skill).xp_points,
             game_loop.call_count,
             Notification.objects.filter(user=child, notification_type="milestone_completed").count(),
             ActivityEvent.objects.filter(event_type="milestone.complete", target_id=milestone.pk).count()),
            ([Decimal("5.00")], 23, 1, 1, 1),
        )
        milestone.refresh_from_db()
        self.assertTrue(milestone.is_completed)
        self.assertIsNotNone(milestone.completed_at)
