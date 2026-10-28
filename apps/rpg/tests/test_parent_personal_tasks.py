from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreNotAvailableError, ChoreService
from apps.notifications.models import Notification
from apps.quests.models import ChallengeEnrollment
from apps.rewards.models import CoinLedger
from apps.rpg.models import PerfectDayReceipt
from apps.rpg.tasks import evaluate_perfect_day_task, streak_at_risk_warning_task
from config.tests.factories import make_family


class ParentPersonalTaskTests(TestCase):
    def setUp(self):
        household = make_family("Personal task family", parents=[{"username": "task-parent"}, {"username": "task-coparent"}])
        self.parent, self.coparent = household.parents
        ChallengeEnrollment.objects.create(user=self.parent)

    def test_enrolled_parent_earns_own_perfect_day_once_without_shared_chores_or_family_payout(self):
        today = timezone.localdate()
        profile = self.parent.character_profile
        profile.last_active_date = today
        profile.save(update_fields=["last_active_date"])
        chore = Chore.objects.create(title="My daily tidy", recurrence="daily", assigned_to=self.parent, created_by=self.parent, family=self.parent.family)
        ChoreCompletion.objects.create(chore=chore, user=self.parent, completed_date=today, status="approved",
                                       reward_amount_snapshot=0, coin_reward_snapshot=0)
        shared = Chore.objects.create(title="Shared tidy", recurrence="daily", assigned_to=None,
                                      created_by=self.parent, family=self.parent.family)
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.parent, shared, personal=True)
        evaluate_perfect_day_task()
        evaluate_perfect_day_task()
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.parent).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, description="Perfect Day bonus!").count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.coparent).exists())

    def test_child_still_requires_approved_shared_daily_chores_for_perfect_day(self):
        child = type(self.parent).objects.create_user(username="task-child", role="child", family=self.parent.family)
        today = timezone.localdate()
        profile = child.character_profile
        profile.last_active_date = today
        profile.save(update_fields=["last_active_date"])
        own = Chore.objects.create(title="Child daily tidy", recurrence="daily", assigned_to=child,
                                   created_by=self.parent, family=child.family)
        shared = Chore.objects.create(title="Shared tidy", recurrence="daily", assigned_to=None,
                                      created_by=self.parent, family=child.family)
        ChoreCompletion.objects.create(chore=own, user=child, completed_date=today, status="approved",
                                       reward_amount_snapshot=0, coin_reward_snapshot=0)
        evaluate_perfect_day_task()
        self.assertFalse(PerfectDayReceipt.objects.filter(user=child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=child, description="Perfect Day bonus!").exists())
        ChoreCompletion.objects.create(chore=shared, user=child, completed_date=today, status="approved",
                                       reward_amount_snapshot=0, coin_reward_snapshot=0)
        evaluate_perfect_day_task()
        evaluate_perfect_day_task()
        self.assertEqual(PerfectDayReceipt.objects.filter(user=child).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=child, description="Perfect Day bonus!", amount=15).count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user__in=[self.parent, self.coparent]).exists())

    def test_only_participating_parent_gets_own_streak_reminder_once(self):
        for parent in (self.parent, self.coparent):
            profile = parent.character_profile
            profile.login_streak = 5
            profile.last_active_date = timezone.localdate() - timedelta(days=1)
            profile.save(update_fields=["login_streak", "last_active_date"])
        streak_at_risk_warning_task()
        streak_at_risk_warning_task()
        self.assertEqual(Notification.objects.filter(user=self.parent, notification_type="streak_at_risk").count(), 1)
        self.assertFalse(Notification.objects.filter(user=self.coparent).exists())

    def test_parent_streak_reminder_suggests_personal_activities_and_push_opens_my_space(self):
        profile = self.parent.character_profile
        profile.login_streak = 5
        profile.last_active_date = timezone.localdate() - timedelta(days=1)
        profile.save(update_fields=["login_streak", "last_active_date"])

        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push:
            streak_at_risk_warning_task()
            streak_at_risk_warning_task()

        note = Notification.objects.get(user=self.parent, notification_type="streak_at_risk")
        with self.subTest(surface="activity_copy"):
            self.assertIn("5-day streak", note.message)
            self.assertNotIn("homework", note.message.lower())
            for activity in ("your chores", "habit", "reading", "movement", "My space"):
                self.assertIn(activity, note.message)
        with self.subTest(surface="saved_destination"):
            self.assertEqual(note.link, "/quests?space=personal")
        with self.subTest(surface="push_destination"):
            push.assert_called_once_with(
                self.parent.pk, note.title, note.message, "/quests?space=personal", "streak_at_risk",
            )
        self.assertFalse(Notification.objects.filter(user=self.coparent).exists())

    def test_child_streak_reminder_retains_existing_activity_copy_and_destination(self):
        child = type(self.parent).objects.create_user(
            username="reminder-child", role="child", family=self.parent.family,
        )
        profile = child.character_profile
        profile.login_streak = 5
        profile.last_active_date = timezone.localdate() - timedelta(days=1)
        profile.save(update_fields=["login_streak", "last_active_date"])

        streak_at_risk_warning_task()

        note = Notification.objects.get(user=child, notification_type="streak_at_risk")
        self.assertEqual(note.message, (
            "Your 5-day streak ends tonight unless you log something — "
            "a chore, a habit tap, or homework counts."
        ))
        self.assertEqual(note.link, "/quests")
        self.assertFalse(Notification.objects.filter(user__in=[self.parent, self.coparent]).exists())
