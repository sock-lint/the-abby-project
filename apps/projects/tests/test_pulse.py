"""Tests for ``apps.projects.pulse`` — the single-heartbeat payload that
replaced eight independent frontend pollers.

The contract that matters: every block the shell's hooks used to fetch from
its own endpoint is present and shaped the same, the payload is cheap enough
to run every 30 seconds forever, and it never leaks another household's rows.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.projects.models import Project, SavingsGoal
from apps.projects.pulse import build_pulse
from apps.rpg.models import CharacterProfile
from apps.rpg.services import GameLoopService, StreakService
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family

# The pulse runs on a 30s loop for every signed-in family member, so a
# regression that fans it out into per-item queries is a real cost. This is a
# ceiling, not a target — tighten it if the payload gets cheaper.
MAX_PULSE_QUERIES = 40


class PulsePayloadTests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Pulse House",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.family.parents[0]
        self.child = self.family.children[0]

    def test_carries_every_block_the_shell_polls_for(self):
        payload = build_pulse(self.child)
        for key in (
            "unread_count",
            "notifications",
            "recent_drops",
            "active_quest",
            "companion_growth",
            "expeditions_ready",
            "savings_goals",
            "newly_unlocked_lorebook",
            "header",
        ):
            self.assertIn(key, payload, f"pulse is missing the {key} block")

    def test_header_block_carries_the_sticky_pip_values(self):
        header = build_pulse(self.child)["header"]
        self.assertIn("active_timer", header)
        self.assertIn("coin_balance", header)
        self.assertIn("streak_days", header)

    def test_unread_count_matches_the_notification_feed(self):
        Notification.objects.create(
            user=self.child, title="Chore approved", message="Dishes",
            notification_type="chore_approved",
        )
        Notification.objects.create(
            user=self.child, title="Seen already", message="",
            notification_type="chore_approved", is_read=True,
        )
        payload = build_pulse(self.child)
        self.assertEqual(payload["unread_count"], 1)
        # The list carries read rows too — the bell renders both.
        self.assertEqual(len(payload["notifications"]), 2)

    def test_notifications_are_capped(self):
        for i in range(30):
            Notification.objects.create(
                user=self.child, title=f"n{i}", message="",
                notification_type="chore_approved",
            )
        self.assertEqual(len(build_pulse(self.child)["notifications"]), 20)

    def test_savings_goals_include_completed_ones(self):
        # The completion toast hook diffs on `is_completed`, so unlike the
        # dashboard block (which filters to open goals) the pulse must carry
        # completed goals too or the toast can never fire.
        SavingsGoal.objects.create(
            user=self.child, title="Bike", target_amount="100.00", is_completed=True,
        )
        titles = [g["title"] for g in build_pulse(self.child)["savings_goals"]]
        self.assertIn("Bike", titles)

    def test_parent_skips_the_child_only_blocks(self):
        payload = build_pulse(self.parent)
        # Parents have no personal quest, growth queue, or lorebook unlocks;
        # computing them would be wasted work on every beat.
        self.assertIsNone(payload["active_quest"])
        self.assertEqual(payload["newly_unlocked_lorebook"], [])

    def test_stays_within_the_query_budget(self):
        build_pulse(self.child)  # warm any lazy imports / content caches
        with CaptureQueriesContext(connection) as ctx:
            build_pulse(self.child)
        self.assertLessEqual(
            len(ctx.captured_queries),
            MAX_PULSE_QUERIES,
            f"pulse ran {len(ctx.captured_queries)} queries; it polls every 30s",
        )

    def test_does_not_stamp_last_seen(self):
        # The dashboard stamps ``last_seen_at`` on every fetch. If the pulse
        # did too it would continuously reset the since-last-visit window that
        # the child dashboard's welcome-back card depends on.
        self.child.refresh_from_db()
        before = self.child.last_seen_at
        build_pulse(self.child)
        self.child.refresh_from_db()
        self.assertEqual(self.child.last_seen_at, before)


class PulseViewTests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Pulse House",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.child = self.family.children[0]
        self.client = APIClient()

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(reverse("pulse")).status_code, 401)

    def test_returns_the_payload_for_the_requesting_user(self):
        self.client.force_authenticate(user=self.child)
        response = self.client.get(reverse("pulse"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("unread_count", response.data)
        self.assertIn("header", response.data)

    def test_is_self_scoped(self):
        other = make_family(
            "Another House", parents=[{"username": "p2"}], children=[{"username": "k2"}],
        )
        Notification.objects.create(
            user=other.children[0], title="Not yours", message="",
            notification_type="chore_approved",
        )
        self.client.force_authenticate(user=self.child)
        response = self.client.get(reverse("pulse"))
        titles = [n["title"] for n in response.data["notifications"]]
        self.assertNotIn("Not yours", titles)
        self.assertEqual(response.data["unread_count"], 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PulseActivityStreakTests(TestCase):
    def setUp(self):
        self.clock = patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 10, 21, 19, tzinfo=datetime_timezone.utc),
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.today = timezone.localdate()
        household = make_family(
            "Activity Streak House",
            parents=[{"username": "activity-parent"}],
            children=[{"username": "activity-child"}],
        )
        self.parent = household.parents[0]
        self.child = household.children[0]
        self.client = APIClient()
        token = Token.objects.create(user=self.child)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def record_four_activity_days(self, *, ending_days_ago=0):
        for days_ago in range(ending_days_ago + 3, ending_days_ago - 1, -1):
            StreakService.record_activity(
                self.child, activity_date=self.today - timedelta(days=days_ago),
            )

    def create_two_work_days(self):
        project = Project.objects.create(
            title="Work timer history", created_by=self.parent, assigned_to=self.child,
            status="in_progress",
        )
        for days_ago in range(2):
            clock_out = timezone.now() - timedelta(days=days_ago)
            TimeEntry.objects.create(
                user=self.child, project=project,
                clock_in=clock_out - timedelta(minutes=10), clock_out=clock_out,
                status="completed",
            )

    def assert_streak_matches_dashboard(self, expected):
        dashboard = self.client.get(reverse("dashboard"))
        pulse = self.client.get(reverse("pulse"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(pulse.status_code, 200)
        self.assertEqual(dashboard.data["rpg"]["login_streak"], expected)
        self.assertEqual(pulse.data["header"]["streak_days"], expected)
        return dashboard.data

    def test_header_matches_four_day_activity_streak_without_work_timers(self):
        self.record_four_activity_days()
        self.assertFalse(TimeEntry.objects.filter(user=self.child).exists())
        self.assert_streak_matches_dashboard(4)

    def test_header_uses_activity_streak_when_work_timer_streak_disagrees(self):
        self.record_four_activity_days()
        self.create_two_work_days()
        dashboard = self.assert_streak_matches_dashboard(4)
        # The separate work-time report retains its existing meaning.
        self.assertEqual(dashboard["streak_days"], 2)

    def test_zero_activity_streak_is_not_replaced_with_work_timer_history(self):
        self.create_two_work_days()
        self.assert_streak_matches_dashboard(0)

    def test_header_reflects_a_reset_activity_streak(self):
        self.record_four_activity_days(ending_days_ago=3)
        self.create_two_work_days()
        result = StreakService.record_activity(self.child, activity_date=self.today)
        self.assertTrue(result["streak_broken"])
        self.assert_streak_matches_dashboard(1)

    def test_header_does_not_use_another_family_members_activity_streak(self):
        self.record_four_activity_days()
        other = make_family(
            "Other Activity House", children=[{"username": "other-activity-child"}],
        ).children[0]
        CharacterProfile.objects.filter(user=self.parent).update(login_streak=8)
        CharacterProfile.objects.filter(user=other).update(login_streak=12)
        response = self.client.get(reverse("pulse"), {"user_id": other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["header"]["streak_days"], 4)

    def test_missing_profile_returns_zero_without_creating_streak_state(self):
        CharacterProfile.objects.filter(user=self.child).delete()
        response = self.client.get(reverse("pulse"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["header"]["streak_days"], 0)
        self.assertFalse(CharacterProfile.objects.filter(user=self.child).exists())

    def test_active_bonus_matches_real_check_in_at_growth_and_cap_boundaries(self):
        from apps.rewards.services import CoinService

        for days, multiplier, coins, drop_bonus, intensity in (
            (1, 1.1, 5, 0.05, 0.05),
            (5, 1.5, 7, 0.25, 0.25),
            (9, 1.9, 9, 0.45, 0.45),
            (10, 2.0, 10, 0.5, 0.5),
            (19, 2.9, 14, 0.5, 0.95),
            (20, 3.0, 15, 0.5, 1.0),
            (40, 3.0, 15, 0.5, 1.0),
        ):
            with self.subTest(days=days):
                CharacterProfile.objects.filter(user=self.child).update(
                    login_streak=days - 1,
                    last_active_date=self.today - timedelta(days=1),
                )
                before_coins = CoinService.get_balance(self.child)
                event = GameLoopService.on_task_completed(self.child, "daily_check_in")
                self.assertEqual(event["streak"]["streak"], days)
                self.assertEqual(event["streak"]["check_in_bonus_coins"], coins)
                self.assertEqual(CoinService.get_balance(self.child) - before_coins, coins)
                expected = {
                    "active_today": True,
                    "check_in_multiplier": multiplier,
                    "check_in_coins": coins,
                    "drop_bonus": drop_bonus,
                    "intensity": intensity,
                }
                header = self.client.get(reverse("pulse")).data["header"]
                rpg = self.client.get(reverse("dashboard")).data["rpg"]
                self.assertEqual(header["streak_bonus"], expected)
                self.assertEqual(rpg["streak_bonus"], expected)

    def test_inactive_streak_keeps_saved_days_without_claiming_a_bonus(self):
        inactive = {
            "active_today": False,
            "check_in_multiplier": 1.0,
            "check_in_coins": 0,
            "drop_bonus": 0.0,
            "intensity": 0.0,
        }
        for days_ago, freeze, days in (
            (1, None, 20),
            (4, None, 20),
            (4, self.today + timedelta(days=1), 20),
            (0, None, 0),
            (None, None, 20),
            (-1, None, 20),
        ):
            with self.subTest(days_ago=days_ago, freeze=freeze, days=days):
                CharacterProfile.objects.filter(user=self.child).update(
                    login_streak=days,
                    last_active_date=None if days_ago is None else self.today - timedelta(days=days_ago),
                    streak_freeze_expires_at=freeze,
                )
                header = self.client.get(reverse("pulse")).data["header"]
                rpg = self.client.get(reverse("dashboard")).data["rpg"]
                self.assertEqual(header["streak_days"], days)
                self.assertEqual(rpg["login_streak"], days)
                self.assertEqual(header["streak_bonus"], inactive)
                self.assertEqual(rpg["streak_bonus"], inactive)

    def test_projected_drop_bonus_matches_real_roll_threshold_and_cap(self):
        from apps.rpg.models import DropTable, ItemDefinition, UserInventory

        item = ItemDefinition.objects.create(
            slug="header-bonus-food", name="Bonus test food", item_type="food", rarity="common",
        )
        DropTable.objects.create(trigger_type="chore_complete", item=item, weight=1, min_level=0)
        for days, drop_bonus, hit, miss in (
            (5, 0.25, 0.54, 0.56), (10, 0.5, 0.79, 0.81), (40, 0.5, 0.79, 0.81),
        ):
            with self.subTest(days=days):
                CharacterProfile.objects.filter(user=self.child).update(
                    login_streak=days, last_active_date=self.today,
                )
                bonus = self.client.get(reverse("pulse")).data["header"]["streak_bonus"]
                self.assertEqual(bonus["drop_bonus"], drop_bonus)
                before = UserInventory.objects.filter(user=self.child, item=item).values_list(
                    "quantity", flat=True,
                ).first() or 0
                with patch("apps.rpg.services.random.random", return_value=hit):
                    event = GameLoopService.on_task_completed(self.child, "chore_complete")
                self.assertEqual([entry["item_id"] for entry in event["drops"]], [item.pk])
                with patch("apps.rpg.services.random.random", return_value=miss):
                    event = GameLoopService.on_task_completed(self.child, "chore_complete")
                self.assertEqual(event["drops"], [])
                self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, before + 1)

    def test_bonus_reads_preserve_streak_rewards_and_activity(self):
        from apps.activity.models import ActivityEvent
        from apps.rewards.models import CoinLedger

        for days_ago in (0, 1, 4):
            with self.subTest(days_ago=days_ago):
                CharacterProfile.objects.filter(user=self.child).update(
                    login_streak=20,
                    last_active_date=self.today - timedelta(days=days_ago),
                    streak_freeze_expires_at=self.today + timedelta(days=1),
                )
                before = CharacterProfile.objects.filter(user=self.child).values().get()
                before_coins = CoinLedger.objects.count()
                before_activity = ActivityEvent.objects.count()
                for endpoint in ("pulse", "dashboard"):
                    response = self.client.get(reverse(endpoint))
                    self.assertEqual(response.status_code, 200)
                    block = response.data["header" if endpoint == "pulse" else "rpg"]
                    self.assertIn("streak_bonus", block)
                self.assertEqual(CharacterProfile.objects.filter(user=self.child).values().get(), before)
                self.assertEqual(CoinLedger.objects.count(), before_coins)
                self.assertEqual(ActivityEvent.objects.count(), before_activity)

    def test_bonus_uses_the_server_streak_date_near_utc_midnight(self):
        # UTC has advanced to October 22; the actual streak day in Phoenix
        # remains October 21. Family and browser timezones cannot advance it.
        CharacterProfile.objects.filter(user=self.child).update(
            login_streak=5, last_active_date=self.today,
        )
        self.family = self.child.family
        self.family.timezone = "Pacific/Auckland"
        self.family.save(update_fields=["timezone"])
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 22, 1, tzinfo=datetime_timezone.utc)):
            for endpoint in ("pulse", "dashboard"):
                response = self.client.get(reverse(endpoint))
                block = response.data["header" if endpoint == "pulse" else "rpg"]
                self.assertTrue(block["streak_bonus"]["active_today"])
                self.assertEqual(block["streak_bonus"]["check_in_multiplier"], 1.5)

    def test_bonus_is_self_scoped_even_when_another_user_is_requested(self):
        CharacterProfile.objects.filter(user=self.child).update(
            login_streak=5, last_active_date=self.today,
        )
        outsider = make_family(
            "Other Bonus House", children=[{"username": "other-bonus-child"}],
        ).children[0]
        for other in (self.parent, outsider):
            CharacterProfile.objects.filter(user=other).update(
                login_streak=40, last_active_date=self.today,
            )
            for endpoint in ("pulse", "dashboard"):
                response = self.client.get(reverse(endpoint), {"user_id": other.pk})
                self.assertEqual(response.status_code, 200)
                block = response.data["header" if endpoint == "pulse" else "rpg"]
                self.assertEqual(block["streak_bonus"]["check_in_multiplier"], 1.5)

    def test_missing_profile_has_no_bonus_and_pulse_does_not_create_one(self):
        CharacterProfile.objects.filter(user=self.child).delete()
        header = self.client.get(reverse("pulse")).data["header"]
        self.assertEqual(header["streak_bonus"], {
            "active_today": False, "check_in_multiplier": 1.0,
            "check_in_coins": 0, "drop_bonus": 0.0, "intensity": 0.0,
        })
        self.assertFalse(CharacterProfile.objects.filter(user=self.child).exists())
