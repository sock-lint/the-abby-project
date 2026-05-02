from django.test import TestCase, override_settings

from apps.habits.models import Habit
from apps.habits.tasks import decay_habit_strength_task
from apps.projects.models import User
from config.tests.factories import make_family


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

    def test_decay_does_not_touch_parent_habits(self):
        """Parent users' rows must never decay — only children own habits."""
        parent_habit = Habit.objects.create(
            name="Parent journal",
            habit_type="positive",
            user=self.parent,
            created_by=self.parent,
            strength=5,
        )
        decay_habit_strength_task()
        parent_habit.refresh_from_db()
        self.assertEqual(parent_habit.strength, 5)

    def test_decay_runs_across_every_family(self):
        """The Beat task is system-wide; every family's children must decay."""
        family_a = make_family(
            "Adams",
            parents=[{"username": "adams-mom"}],
            children=[{"username": "adams-kid"}],
        )
        family_b = make_family(
            "Bakers",
            parents=[{"username": "bakers-dad"}],
            children=[{"username": "bakers-kid"}],
        )
        habit_a = Habit.objects.create(
            name="A", habit_type="positive",
            user=family_a.children[0], created_by=family_a.parents[0],
            strength=4,
        )
        habit_b = Habit.objects.create(
            name="B", habit_type="positive",
            user=family_b.children[0], created_by=family_b.parents[0],
            strength=4,
        )

        decay_habit_strength_task()

        habit_a.refresh_from_db()
        habit_b.refresh_from_db()
        self.assertEqual(habit_a.strength, 3)
        self.assertEqual(habit_b.strength, 3)
