"""Tests for ``apps.projects.pulse`` — the single-heartbeat payload that
replaced eight independent frontend pollers.

The contract that matters: every block the shell's hooks used to fetch from
its own endpoint is present and shaped the same, the payload is cheap enough
to run every 30 seconds forever, and it never leaks another household's rows.
"""
from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.projects.models import SavingsGoal
from apps.projects.pulse import build_pulse
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
