"""Force one of the three CelebrationModal-driving notifications.

Inserts a ``Notification`` row of the right ``notification_type`` so the
frontend's App-boot poll on ``/api/notifications/pending-celebration/``
picks it up on the next mount.

Examples::

    python manage.py force_celebration --user abby --type streak_milestone --days 30
    python manage.py force_celebration --user abby --type perfect_day
    python manage.py force_celebration --user abby --type birthday
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import OperationError, force_celebration


_TYPES = ("streak_milestone", "perfect_day", "birthday")


class Command(BaseCommand):
    help = "Force a CelebrationModal / BirthdayCelebrationModal trigger."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--type", choices=_TYPES, required=True, dest="kind",
            help="Which celebration to fire.",
        )
        parser.add_argument(
            "--days", type=int, default=30,
            help="For streak_milestone: streak count (must be in {3,7,14,30,60,100}).",
        )
        parser.add_argument(
            "--gift-coins", type=int, default=500,
            help="For birthday: number of gift coins to embed in metadata.",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        kind = opts["kind"]

        if kind == "streak_milestone" and opts["days"] not in {3, 7, 14, 30, 60, 100}:
            self.stdout.write(self.style.WARNING(
                f"--days={opts['days']} is not a real milestone "
                "(3/7/14/30/60/100). Notification will still fire — "
                "modal copy may read oddly."
            ))

        try:
            result = force_celebration(
                user, kind=kind, days=opts["days"], gift_coins=opts["gift_coins"],
            )
        except OperationError as e:
            raise CommandError(str(e)) from e

        if kind == "streak_milestone":
            self.stdout.write(self.style.SUCCESS(
                f"Streak milestone notification ({result['days']}d) → {user.username}"
            ))
        elif kind == "perfect_day":
            self.stdout.write(self.style.SUCCESS(
                f"Perfect day notification → {user.username}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Birthday chronicle entry "
                f"(id={result['chronicle_entry_id']}, "
                f"+{result['gift_coins']} coins) → {user.username}"
            ))
