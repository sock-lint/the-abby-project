from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.habits.models import Habit, HabitLog
from apps.habits.services import HabitService
from apps.habits.tasks import decay_habit_strength_task
from config.tests.factories import make_family


class HabitDailyDecayTests(TestCase):
    def setUp(self):
        household = make_family(
            parents=[{"username": "decay-parent"}],
            children=[{"username": "decay-child"}],
        )
        self.family = household.family
        self.child = household.children[0]
        self.habit = Habit.objects.create(
            name="Daily reading", user=self.child,
            created_by=household.parents[0], strength=3,
        )
        self.midnight = datetime(2026, 10, 16, 0, 5, tzinfo=ZoneInfo("America/Phoenix"))

    def log_at(self, stamp):
        with patch("django.utils.timezone.now", return_value=stamp):
            HabitLog.objects.create(habit=self.habit, user=self.child, direction=1)

    def test_midnight_tick_preserves_previous_days_tap(self):
        self.log_at(self.midnight - timedelta(hours=6))
        with patch("django.utils.timezone.now", return_value=self.midnight):
            result = decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 3)
        self.assertIn("0 habits decayed", result)

    def test_new_day_tap_does_not_hide_previous_days_miss(self):
        self.log_at(self.midnight - timedelta(minutes=3))
        with patch("django.utils.timezone.now", return_value=self.midnight):
            decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 2)

    def test_redelivery_decays_each_completed_day_only_once(self):
        with patch("django.utils.timezone.now", return_value=self.midnight):
            first = decay_habit_strength_task()
            second = decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 2)
        self.assertIn("1 habits decayed", first)
        self.assertIn("0 habits decayed", second)
        self.assertEqual(self.habit.last_decay_date, date(2026, 10, 15))

    def test_next_completed_day_can_decay_again(self):
        with patch("django.utils.timezone.now", return_value=self.midnight):
            decay_habit_strength_task()
        with patch("django.utils.timezone.now", return_value=self.midnight + timedelta(days=1)):
            decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 1)

    def test_family_local_completed_day_controls_tap_lookup(self):
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        # Oct 16 in Tokyo and Oct 15 on the server. The Oct 15 evening tap
        # belongs to Tokyo's completed day and must protect this habit.
        self.log_at(datetime(2026, 10, 14, 16, tzinfo=datetime_timezone.utc))
        tick = datetime(2026, 10, 15, 15, 5, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=tick):
            decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 3)
        self.assertEqual(self.habit.last_decay_date, date(2026, 10, 15))

    def test_zero_and_tapped_habits_are_still_marked_processed(self):
        self.habit.strength = 0
        self.habit.save(update_fields=["strength"])
        target = date(2026, 10, 15)
        self.assertEqual(HabitService.decay_all_habits(self.child, target), 0)
        self.habit.strength = 4
        self.habit.save(update_fields=["strength"])
        self.assertEqual(HabitService.decay_all_habits(self.child, target), 0)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 4)

    def test_negative_strength_and_scaling_remain_toward_zero(self):
        self.habit.strength = -3
        self.habit.max_taps_per_day = 4
        self.habit.save(update_fields=["strength", "max_taps_per_day"])
        self.assertEqual(HabitService.decay_all_habits(self.child, date(2026, 10, 15)), 1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, -1)

    def test_failed_decay_does_not_consume_day(self):
        save = Habit.save

        def fail_after_write(instance, *args, **kwargs):
            save(instance, *args, **kwargs)
            raise RuntimeError("storage failed")

        with patch.object(Habit, "save", fail_after_write):
            with self.assertRaisesMessage(RuntimeError, "storage failed"):
                HabitService.decay_all_habits(self.child, date(2026, 10, 15))
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 3)
        self.assertEqual(HabitService.decay_all_habits(self.child, date(2026, 10, 15)), 1)


class HabitDecayConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_deliveries_evaluate_one_day_once(self):
        household = make_family(
            parents=[{"username": "parallel-decay-parent"}],
            children=[{"username": "parallel-decay-child"}],
        )
        child = household.children[0]
        habit = Habit.objects.create(
            name="Read", user=child, created_by=household.parents[0], strength=4,
        )
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return HabitService.decay_all_habits(child, date(2026, 10, 15))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: run(), range(2)))
        habit.refresh_from_db()
        self.assertEqual(habit.strength, 3)
        self.assertEqual(sum(counts), 1)
