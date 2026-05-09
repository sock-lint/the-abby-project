"""Set a user's streak counters to a specific value.

Pre-bakes a ``CharacterProfile`` row to a chosen ``login_streak`` (and
optionally ``perfect_days_count``) without grinding through N days of
activity. ``last_active_date`` is set to today so the next legitimate
activity continues the streak rather than triggering the gap-recovery
path.

Examples::

    python manage.py set_streak --user abby --days 29
    python manage.py set_streak --user abby --days 99 --perfect-days 12
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import set_streak


class Command(BaseCommand):
    help = "Set login_streak (+ optional perfect_days_count) on a user's CharacterProfile."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument("--days", type=int, required=True)
        parser.add_argument(
            "--perfect-days", type=int, default=None, dest="perfect_days",
            help="Optional: also set perfect_days_count.",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        result = set_streak(user, days=opts["days"], perfect_days=opts["perfect_days"])

        msg = f"login_streak={result['login_streak']}"
        if opts["perfect_days"] is not None:
            msg += f", perfect_days_count={result['perfect_days_count']}"
        self.stdout.write(self.style.SUCCESS(f"{msg} → {user.username}"))
