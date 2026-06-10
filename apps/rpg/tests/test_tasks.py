from datetime import date

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rpg.tasks import evaluate_perfect_day_task


# Tests should never reach the production Redis cache. Swap in an in-memory
# backend so notification side effects (and any other cache touches) don't
# block on a Redis connection.
CACHES_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(
    CACHES=CACHES_OVERRIDE,
    # Run Celery tasks synchronously so creating a Chore doesn't try to
    # enqueue the google_integration sync task against a real broker.
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class PerfectDayTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="pdparent", password="testpass", role="parent"
        )
        self.child = User.objects.create_user(
            username="pdchild", password="testpass", role="child"
        )
        # CharacterProfile is auto-created by post_save signal on User; we
        # only need to seed last_active_date.
        self.profile = self.child.character_profile
        self.profile.last_active_date = timezone.localdate()
        self.profile.save(update_fields=["last_active_date"])

    def test_perfect_day_with_all_chores_done(self):
        """Active user with all daily chores approved gets perfect day."""
        chore = Chore.objects.create(
            title="Make bed",
            recurrence=Chore.Recurrence.DAILY,
            assigned_to=self.child,
            created_by=self.parent,
        )
        # Mark chore as completed today
        ChoreCompletion.objects.create(
            chore=chore,
            user=self.child,
            completed_date=timezone.localdate(),
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=chore.reward_amount,
            coin_reward_snapshot=chore.coin_reward,
        )

        result = evaluate_perfect_day_task()
        self.assertIn("1/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)

    def test_not_perfect_if_inactive(self):
        """User not active today gets no perfect day."""
        self.profile.last_active_date = date(2026, 1, 1)
        self.profile.save(update_fields=["last_active_date"])

        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)

    def test_no_perfect_day_when_no_daily_chores_configured(self):
        """Active child with zero daily chores must not earn a perfect day."""
        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)
        self.assertEqual(
            CoinLedger.objects.filter(user=self.child).count(), 0,
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.child, notification_type="perfect_day",
            ).exists(),
        )

    def test_no_perfect_day_with_partial_completion(self):
        """Two daily chores, only one approved, no perfect day."""
        chore_a = Chore.objects.create(
            title="Make bed",
            recurrence=Chore.Recurrence.DAILY,
            assigned_to=self.child,
            created_by=self.parent,
        )
        Chore.objects.create(
            title="Brush teeth",
            recurrence=Chore.Recurrence.DAILY,
            assigned_to=self.child,
            created_by=self.parent,
        )
        ChoreCompletion.objects.create(
            chore=chore_a,
            user=self.child,
            completed_date=timezone.localdate(),
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=chore_a.reward_amount,
            coin_reward_snapshot=chore_a.coin_reward,
        )

        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)

    def test_rejected_completion_does_not_count(self):
        """A REJECTED completion leaves the chore unfinished — no perfect day."""
        chore = Chore.objects.create(
            title="Make bed",
            recurrence=Chore.Recurrence.DAILY,
            assigned_to=self.child,
            created_by=self.parent,
        )
        ChoreCompletion.objects.create(
            chore=chore,
            user=self.child,
            completed_date=timezone.localdate(),
            status=ChoreCompletion.Status.REJECTED,
            reward_amount_snapshot=chore.reward_amount,
            coin_reward_snapshot=chore.coin_reward,
        )

        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)

    def test_only_weekly_chore_no_perfect_day(self):
        """Weekly chores don't satisfy the daily-chore requirement."""
        Chore.objects.create(
            title="Mow lawn",
            recurrence=Chore.Recurrence.WEEKLY,
            assigned_to=self.child,
            created_by=self.parent,
        )

        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)




@override_settings(
    CACHES=CACHES_OVERRIDE,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class StreakAtRiskWarningTaskTests(TestCase):
    """19:00 preventative streak warning — fires once per local day for
    kids with streak >= 3 who haven't logged anything today."""

    def setUp(self):
        from apps.rpg.tasks import streak_at_risk_warning_task
        self.task = streak_at_risk_warning_task
        self.child = User.objects.create_user(
            username="sarchild", password="testpass", role="child"
        )
        self.profile = self.child.character_profile
        self.today = timezone.localdate()
        self.yesterday = self.today - timezone.timedelta(days=1)

    def _arm(self, streak=5, last_active=None, freeze=None):
        self.profile.login_streak = streak
        self.profile.last_active_date = (
            last_active if last_active is not None else self.yesterday
        )
        self.profile.streak_freeze_expires_at = freeze
        self.profile.save(
            update_fields=[
                "login_streak", "last_active_date", "streak_freeze_expires_at",
            ],
        )

    def _warnings(self):
        return Notification.objects.filter(
            user=self.child, notification_type="streak_at_risk",
        )

    def test_warns_idle_child_with_streak(self):
        self._arm(streak=5)
        self.task()

        self.assertEqual(self._warnings().count(), 1)
        note = self._warnings().get()
        self.assertIn("5-day streak", note.message)
        self.assertEqual(note.link, "/quests")

    def test_skips_streak_below_minimum(self):
        self._arm(streak=2)
        self.task()
        self.assertEqual(self._warnings().count(), 0)

    def test_skips_child_already_active_today(self):
        self._arm(streak=5, last_active=self.today)
        self.task()
        self.assertEqual(self._warnings().count(), 0)

    def test_skips_child_with_no_activity_history(self):
        self.profile.login_streak = 5
        self.profile.last_active_date = None
        self.profile.save(update_fields=["login_streak", "last_active_date"])
        self.task()
        self.assertEqual(self._warnings().count(), 0)

    def test_skips_child_with_armed_freeze_covering_today(self):
        self._arm(streak=5, freeze=self.today)
        self.task()
        self.assertEqual(self._warnings().count(), 0)

    def test_warns_when_freeze_already_expired(self):
        self._arm(streak=5, freeze=self.yesterday)
        self.task()
        self.assertEqual(self._warnings().count(), 1)

    def test_second_run_same_day_does_not_duplicate(self):
        self._arm(streak=5)
        self.task()
        self.task()
        self.assertEqual(self._warnings().count(), 1)

    def test_no_parent_fanout(self):
        parent = User.objects.create_user(
            username="sarparent", password="testpass", role="parent"
        )
        self._arm(streak=5)
        self.task()
        self.assertEqual(
            Notification.objects.filter(user=parent).count(), 0,
        )
