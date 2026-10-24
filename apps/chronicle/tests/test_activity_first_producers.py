"""Real activity producers preserve both source and streak first recognitions."""
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activity.models import ActivityEvent
from apps.chronicle.firsts import slug_for
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.habits.models import Habit
from apps.notifications.models import Notification, NotificationType
from apps.projects.models import Project, ProjectCompletionRewardReceipt
from apps.quests.models import ChallengeActivity, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import CharacterProfile
from apps.rpg.services import GameLoopService, StreakService
from config.tests.factories import make_family


class ActivityFirstProducerTests(TestCase):
    def setUp(self):
        family = make_family(
            "Activity recognition family", parents=[{"username": "first-producer-parent"}],
            children=[{"username": f"first-producer-child-{n}"} for n in range(3)],
        )
        self.parent = family.parents[0]
        self.child = family.children[0]
        self.children = family.children

    def approaching_streak(self, target, child=None):
        profile = CharacterProfile.objects.get(user=child or self.child)
        profile.login_streak = target - 1
        profile.longest_login_streak = target - 1
        profile.last_active_date = timezone.localdate() - timedelta(days=1)
        profile.save(update_fields=["login_streak", "longest_login_streak", "last_active_date"])
        return profile

    def project(self, payment_kind="bounty"):
        return Project.objects.create(
            title="Saved recognition project", created_by=self.parent, assigned_to=self.child,
            status=Project.Status.ACTIVE, payment_kind=payment_kind,
        )

    def boss(self):
        definition = QuestDefinition.objects.create(
            name="Recognition must not replay work", quest_type="boss", target_value=1_000,
            is_system=True, coin_reward=0, xp_reward=0,
        )
        return QuestService.start_quest(self.child, definition.pk)

    def slugs(self, child=None):
        return set(ChronicleEntry.objects.filter(
            user=child or self.child, kind=ChronicleEntry.Kind.FIRST_EVER,
        ).values_list("event_slug", flat=True))

    def assert_source_awarded_once(self, project, quest):
        project.refresh_from_db()
        quest.refresh_from_db()
        self.assertEqual(project.status, Project.Status.COMPLETED)
        self.assertEqual(ProjectCompletionRewardReceipt.objects.filter(project=project).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BOUNTY_BONUS).count(), 1)
        self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.BOUNTY_BONUS).amount, 25)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, description="Daily check-in bonus").count(), 1)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).login_streak, 30)
        self.assertEqual(quest.current_progress, 75)
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.child).contribution, 75)
        self.assertEqual(ActivityEvent.objects.filter(subject=self.child, event_type="quest.progress").count(), 1)
        self.assertEqual(ChallengeActivity.objects.filter(
            user=self.child, source_type="project_complete", source_id=str(project.pk),
        ).count(), 1)

    def test_bounty_completion_records_bounty_and_streak_firsts_without_replaying_source_rewards(self):
        self.approaching_streak(30)
        quest = self.boss()
        project = self.project()
        with patch.object(StreakService, "record_activity", wraps=StreakService.record_activity) as record_streak:
            project.status = Project.Status.COMPLETED
            project.save()
            project.save()
        record_streak.assert_called_once()

        self.assertSetEqual(self.slugs(), {"first_bounty_payout", "first_streak_30"})
        self.assert_source_awarded_once(project, quest)
        self.assertEqual(Notification.objects.filter(
            user=self.child, notification_type=NotificationType.CHRONICLE_FIRST_EVER,
        ).count(), 2)
        self.assertFalse(ChronicleEntry.objects.filter(user__in=self.children[1:]).exists())

    def test_required_project_keeps_legacy_primary_result_and_records_simultaneous_streak(self):
        self.approaching_streak(60)
        project = self.project(Project.PaymentKind.REQUIRED)
        project.status = Project.Status.COMPLETED
        project.save()

        self.assertSetEqual(self.slugs(), {"first_project_completed", "first_streak_60"})
        context = {"payment_kind": "required", "streak": 60}
        self.assertEqual(slug_for(TriggerType.PROJECT_COMPLETE, context), (
            "first_project_completed", "First project completed", "spark",
        ))
        self.assertEqual(GameLoopService._record_chronicle_firsts(
            self.child, TriggerType.PROJECT_COMPLETE, context,
        ), {"entry_id": None, "event_slug": "first_project_completed"})
        self.assertEqual(Notification.objects.filter(
            user=self.child, notification_type=NotificationType.CHRONICLE_FIRST_EVER,
        ).count(), 2)

    def test_real_positive_habit_actions_record_30_60_100_day_firsts_once_per_child(self):
        for child, target in zip(self.children, (30, 60, 100)):
            with self.subTest(target=target):
                self.approaching_streak(target, child)
                habit = Habit.objects.create(
                    user=child, created_by=self.parent, name=f"Practice toward {target}",
                    xp_reward=0, max_taps_per_day=2,
                )
                client = APIClient()
                client.force_authenticate(child)
                for _ in range(2):
                    response = client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
                    self.assertEqual(response.status_code, 200, response.data)

                self.assertSetEqual(self.slugs(child), {f"first_streak_{target}"})
                self.assertEqual(Notification.objects.filter(
                    user=child, notification_type=NotificationType.CHRONICLE_FIRST_EVER,
                ).count(), 1)
                self.assertEqual(CoinLedger.objects.filter(user=child, description="Daily check-in bonus").count(), 1)
                self.assertEqual(ChallengeActivity.objects.filter(user=child, source_type="habit_log").count(), 2)
                self.assertEqual(CharacterProfile.objects.get(user=child).login_streak, target)

    def test_caller_context_cannot_invent_a_streak_first(self):
        result = GameLoopService.on_task_completed(
            self.child, TriggerType.CLOCK_OUT, {"streak": 100, "drops_allowed": False},
        )

        self.assertEqual(result["streak"]["streak"], 1)
        self.assertFalse(self.slugs())

    def test_failed_streak_step_cannot_fall_back_to_caller_streak_context(self):
        with patch.object(StreakService, "record_activity", side_effect=RuntimeError("Streak storage failed")):
            with self.assertLogs("apps.rpg.services", level="ERROR"):
                result = GameLoopService.on_task_completed(
                    self.child, TriggerType.CLOCK_OUT, {"streak": 100, "drops_allowed": False},
                )

        self.assertIsNone(result["streak"])
        self.assertFalse(self.slugs())
        self.assertFalse(CoinLedger.objects.filter(user=self.child, description="Daily check-in bonus").exists())

    def test_second_first_failure_rolls_back_recognition_but_preserves_source_awards(self):
        self.approaching_streak(30)
        quest = self.boss()
        project = self.project()
        record_first = ChronicleService.record_first

        def fail_streak_first(user, event_slug, **kwargs):
            if event_slug == "first_streak_30":
                self.assertTrue(ChronicleEntry.objects.filter(user=user, event_slug="first_bounty_payout").exists())
                raise RuntimeError("Second first storage failed")
            return record_first(user, event_slug, **kwargs)

        with patch.object(ChronicleService, "record_first", side_effect=fail_streak_first):
            with self.assertLogs("apps.rpg.services", level="ERROR"):
                project.status = Project.Status.COMPLETED
                project.save()

        self.assertFalse(self.slugs())
        self.assertFalse(Notification.objects.filter(
            user=self.child, notification_type=NotificationType.CHRONICLE_FIRST_EVER,
        ).exists())
        self.assert_source_awarded_once(project, quest)

    def test_enclosing_source_rollback_discards_both_firsts_and_all_source_awards(self):
        profile = self.approaching_streak(30)
        quest = self.boss()
        project = self.project()

        with self.assertRaisesRegex(RuntimeError, "Source transaction failed"):
            with transaction.atomic():
                project.status = Project.Status.COMPLETED
                project.save()
                self.assertSetEqual(self.slugs(), {"first_bounty_payout", "first_streak_30"})
                raise RuntimeError("Source transaction failed")

        project.refresh_from_db()
        profile.refresh_from_db()
        quest.refresh_from_db()
        self.assertEqual((project.status, profile.login_streak, quest.current_progress), ("active", 29, 0))
        self.assertFalse(self.slugs())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(ProjectCompletionRewardReceipt.objects.filter(project=project).exists())
        self.assertFalse(Notification.objects.filter(user=self.child).exists())
