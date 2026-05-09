"""Gate enforcement: every command must raise CommandError when DEBUG=False
AND DEV_TOOLS_ENABLED=False, regardless of valid args.

The test pins the contract that lets a production deploy ship safely with
``apps.dev_tools`` in INSTALLED_APPS — invocation either errors out or no-ops.
"""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from config.tests.factories import make_family


class GateOffByDefaultTests(TestCase):
    """When BOTH DEBUG=False and DEV_TOOLS_ENABLED=False, commands raise."""

    def setUp(self) -> None:
        fam = make_family(
            parents=[{"username": "tester"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=False)
    def test_force_drop_blocked(self):
        with self.assertRaises(CommandError) as cm:
            call_command("force_drop", "--user", "abby", "--rarity", "common")
        self.assertIn("disabled", str(cm.exception).lower())

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=False)
    def test_force_celebration_blocked(self):
        with self.assertRaises(CommandError):
            call_command(
                "force_celebration", "--user", "abby", "--type", "perfect_day",
            )

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=False)
    def test_set_streak_blocked(self):
        with self.assertRaises(CommandError):
            call_command("set_streak", "--user", "abby", "--days", "30")

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=False)
    def test_reset_day_counters_blocked(self):
        with self.assertRaises(CommandError):
            call_command("reset_day_counters", "--user", "abby")

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=True)
    def test_explicit_opt_in_unblocks(self):
        # set_streak is the cheapest command to use as the gate-positive
        # smoke — it doesn't need fixture data beyond the user.
        out = StringIO()
        call_command("set_streak", "--user", "abby", "--days", "7", stdout=out)
        self.assertIn("login_streak=7", out.getvalue())

    @override_settings(DEBUG=True, DEV_TOOLS_ENABLED=False)
    def test_debug_alone_unblocks(self):
        out = StringIO()
        call_command("set_streak", "--user", "abby", "--days", "3", stdout=out)
        self.assertIn("login_streak=3", out.getvalue())
