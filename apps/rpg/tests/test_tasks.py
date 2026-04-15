from datetime import date

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.projects.models import User
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


