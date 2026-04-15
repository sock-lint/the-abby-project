from django.test import TestCase, override_settings

from apps.habits.models import Habit
from apps.habits.tasks import decay_habit_strength_task
from apps.projects.models import User


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
class DecayHabitTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="decayparent", password="testpass", role="parent"
        )
        self.child = User.objects.create_user(
            username="decaychild", password="testpass", role="child"
        )

    def test_decay_reduces_untapped_habits(self):
        """Habit with strength=5 decays to 4."""
        habit = Habit.objects.create(
            name="Read",
            habit_type="positive",
            user=self.child,
            created_by=self.parent,
            strength=5,
        )

        result = decay_habit_strength_task()
        self.assertIn("1 habits decayed", result)

        habit.refresh_from_db()
        self.assertEqual(habit.strength, 4)
