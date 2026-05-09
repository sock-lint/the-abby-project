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
from django.utils import timezone

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled


class Command(BaseCommand):
    help = "Set login_streak (+ optional perfect_days_count) on a user's CharacterProfile."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--days", type=int, required=True,
            help="Target login_streak value (1 day from a milestone is the most useful test state).",
        )
        parser.add_argument(
            "--perfect-days", type=int, default=None,
            help="Optional: also set perfect_days_count.",
        )

    def handle(self, *args, **opts):
        assert_enabled()

        from apps.rpg.models import CharacterProfile

        user = resolve_user(opts["user"])
        profile, _created = CharacterProfile.objects.get_or_create(user=user)

        days = opts["days"]
        profile.login_streak = days
        profile.longest_login_streak = max(profile.longest_login_streak, days)
        profile.last_active_date = timezone.localdate()

        update_fields = ["login_streak", "longest_login_streak", "last_active_date"]
        if opts["perfect_days"] is not None:
            profile.perfect_days_count = opts["perfect_days"]
            update_fields.append("perfect_days_count")

        profile.save(update_fields=update_fields)

        msg = f"login_streak={days}"
        if opts["perfect_days"] is not None:
            msg += f", perfect_days_count={opts['perfect_days']}"
        self.stdout.write(self.style.SUCCESS(f"{msg} → {user.username}"))
