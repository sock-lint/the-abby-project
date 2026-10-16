"""Clock splits cannot multiply random rewards for the same saved work day."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings

from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.timecards.models import ClockOutDropReceipt, TimeEntry
from apps.timecards.services import ClockService
from config.tests.factories import make_family


class ClockFixture:
    def setUp(self):
        family = make_family(
            "Clock household", parents=[{"username": "clock-parent"}],
            children=[{"username": "clock-child"}, {"username": "clock-sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.project = Project.objects.create(
            title="Clock work", created_by=self.parent, assigned_to=self.child, status="in_progress",
        )
        self.pouch = ItemDefinition.objects.create(
            slug="clock-pouch", name="Clock pouch", item_type="coin_pouch", icon="C",
        )
        DropTable.objects.create(trigger_type="clock_out", item=self.pouch, weight=1)
        self.now = datetime(2026, 4, 15, 20, tzinfo=dt_timezone.utc)

    def close(self, minutes, *, user=None, project=None, at=None, seconds=0):
        user, project, at = user or self.child, project or self.project, at or self.now
        TimeEntry.objects.create(
            user=user, project=project, clock_in=at - timedelta(minutes=minutes, seconds=seconds), status="active",
        )
        with patch("django.utils.timezone.now", return_value=at), patch("apps.rpg.services.random.random", return_value=0):
            return ClockService.clock_out(user)

    def drops(self, user=None):
        return DropLog.objects.filter(user=user or self.child, trigger_type="clock_out").count()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClockDropIntegrityTests(ClockFixture, TestCase):
    def test_repeated_zero_minute_closes_do_not_award_or_start_game_progress(self):
        for _ in range(3):
            self.assertEqual(self.close(0, seconds=20).duration_minutes, 0)
        self.assertEqual(self.drops(), 0)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertIsNone(CharacterProfile.objects.get(user=self.child).last_active_date)

    def test_tiny_positive_entries_record_activity_without_drop_before_ten_minutes(self):
        for index in range(1, 10):
            self.close(1, at=self.now + timedelta(minutes=index))
        self.assertEqual(self.drops(), 0)
        self.assertIsNotNone(CharacterProfile.objects.get(user=self.child).last_active_date)

    def test_cumulative_ten_minutes_grant_one_opportunity_across_later_splits(self):
        for minutes, expected in ((3, 0), (3, 0), (4, 1), (20, 1)):
            self.close(minutes)
            self.assertEqual(self.drops(), expected)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.pouch).quantity, 1)

    def test_long_and_split_sessions_receive_same_number_of_opportunities(self):
        other_project = Project.objects.create(
            title="Other clock work", created_by=self.parent, assigned_to=self.sibling, status="in_progress",
        )
        self.close(60)
        for minutes in (5, 5, 10, 20, 20):
            self.close(minutes, user=self.sibling, project=other_project)
        self.assertEqual(self.drops(self.child), 1)
        self.assertEqual(self.drops(self.sibling), 1)

    def test_entry_and_project_deletion_cannot_reset_the_saved_daily_opportunity(self):
        self.close(10)
        self.project.delete()
        self.project = Project.objects.create(
            title="Replacement work", created_by=self.parent, assigned_to=self.child, status="in_progress",
        )
        self.close(10)
        self.assertEqual(self.drops(), 1)

    def test_close_day_uses_family_timezone_even_when_clock_in_was_previous_day(self):
        after_midnight = datetime(2026, 4, 16, 7, 5, tzinfo=dt_timezone.utc)
        self.close(10, at=after_midnight)
        self.close(10, at=after_midnight + timedelta(hours=1))
        self.assertEqual(self.drops(), 1)

    def test_new_local_day_rearms_only_that_familys_user(self):
        other = make_family(
            "Eastern clock household", parents=[{"username": "clock-eastern-parent"}],
            children=[{"username": "clock-eastern-child"}],
        )
        other.family.timezone = "Pacific/Kiritimati"
        other.family.save(update_fields=["timezone"])
        eastern = other.children[0]
        eastern_project = Project.objects.create(
            title="Eastern clock work", created_by=other.parents[0], assigned_to=eastern, status="in_progress",
        )
        before = datetime(2026, 4, 16, 6, 55, tzinfo=dt_timezone.utc)
        after = datetime(2026, 4, 16, 7, 15, tzinfo=dt_timezone.utc)
        for at in (before, after):
            self.close(10, at=at)
            self.close(10, user=eastern, project=eastern_project, at=at)
        self.assertEqual(self.drops(), 2)
        self.assertEqual(self.drops(eastern), 1)

    def test_voided_or_homework_minutes_cannot_qualify_a_work_drop(self):
        closed_at = self.now - timedelta(hours=1)
        TimeEntry.objects.create(
            user=self.child, project=self.project, clock_in=closed_at - timedelta(hours=1),
            clock_out=closed_at, status="voided",
        )
        homework = Project.objects.create(
            title="Homework plan", created_by=self.parent, assigned_to=self.child,
            status="in_progress", is_homework_plan=True,
        )
        TimeEntry.objects.create(
            user=self.child, project=homework, clock_in=closed_at - timedelta(hours=1),
            clock_out=closed_at, status="completed",
        )
        self.close(9)
        self.assertEqual(self.drops(), 0)

    def test_failed_hourly_award_rolls_back_close_and_retries_original_entry(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=self.now - timedelta(minutes=60), status="active",
        )
        with patch("django.utils.timezone.now", return_value=self.now), patch(
            "apps.achievements.services.AwardService.grant", side_effect=RuntimeError("synthetic award failure"),
        ):
            with self.assertRaises(RuntimeError):
                ClockService.clock_out(self.child)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "active")
        self.assertIsNone(entry.clock_out)
        with patch("django.utils.timezone.now", return_value=self.now), patch("apps.rpg.services.random.random", return_value=0):
            closed = ClockService.clock_out(self.child)
        self.assertEqual(closed.pk, entry.pk)
        self.assertEqual(self.drops(), 1)

    def test_failed_drop_step_keeps_work_awards_and_later_close_retries_opportunity(self):
        from apps.rpg.services import DropService
        original = DropService.process_drops

        def fail_after_inventory_credit(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic drop storage failure")

        with patch.object(DropService, "process_drops", side_effect=fail_after_inventory_credit):
            saved = self.close(10)
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.duration_minutes, 10)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child, reason="hourly").values_list("amount", flat=True)), [1])
        self.assertFalse(ClockOutDropReceipt.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.pouch).exists())
        self.assertEqual(self.drops(), 0)
        self.close(1, at=self.now + timedelta(minutes=1))
        self.assertEqual(self.drops(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.pouch).quantity, 1)
        self.assertEqual(ClockOutDropReceipt.objects.filter(user=self.child).count(), 1)

    def test_legitimate_random_miss_spends_the_opportunity_without_a_reroll(self):
        at = self.now
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=at - timedelta(minutes=10), status="active",
        )
        with patch("django.utils.timezone.now", return_value=at), patch("apps.rpg.services.random.random", return_value=1):
            ClockService.clock_out(self.child)
        self.assertEqual(self.drops(), 0)
        self.assertEqual(ClockOutDropReceipt.objects.filter(user=self.child).count(), 1)
        self.close(10, at=at + timedelta(minutes=10))
        self.assertEqual(self.drops(), 0)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.pouch).exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClockOutConcurrencyTests(ClockFixture, TransactionTestCase):
    def test_overlapping_clock_outs_close_and_award_only_once(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project, clock_in=self.now - timedelta(minutes=60), status="active",
        )
        ready = Barrier(2)
        read_active = ClockService.get_active_entry

        def synchronized_old_read(user):
            result = read_active(user)
            # On the old nontransactional path both callers can read ACTIVE
            # before either writes. A serialized implementation reads after
            # its transaction/user lock and needs no artificial second reader.
            if not connection.in_atomic_block:
                ready.wait(timeout=5)
            return result

        def close():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                try:
                    return ClockService.clock_out(self.child).pk
                except ValueError as exc:
                    self.assertIn("No active", str(exc))
                    return None
            finally:
                connection.close()

        with patch("django.utils.timezone.now", return_value=self.now), patch(
            "apps.rpg.services.random.random", return_value=0,
        ), patch.object(ClockService, "get_active_entry", side_effect=synchronized_old_read), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(close) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, [entry.pk, None])
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="hourly").count(), 1)
        self.assertEqual(self.drops(), 1)
