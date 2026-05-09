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


_TYPES = ("streak_milestone", "perfect_day", "birthday")


class Command(BaseCommand):
    help = "Force a CelebrationModal / BirthdayCelebrationModal trigger."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--type", choices=_TYPES, required=True,
            help="Which celebration to fire.",
        )
        parser.add_argument(
            "--days", type=int, default=30,
            help="For streak_milestone: the streak count (must be in {3,7,14,30,60,100}).",
        )
        parser.add_argument(
            "--gift-coins", type=int, default=500,
            help="For birthday: number of gift coins to embed in metadata.",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        kind = opts["type"]

        from apps.notifications.models import NotificationType
        from apps.notifications.services import notify

        if kind == "streak_milestone":
            days = opts["days"]
            if days not in {3, 7, 14, 30, 60, 100}:
                self.stdout.write(self.style.WARNING(
                    f"--days={days} is not a real milestone (3/7/14/30/60/100). "
                    "Notification will still fire — modal copy may read oddly."
                ))
            notify(
                user,
                title=f"{days}-day streak!",
                message=f"Lit the journal {days} days running.",
                notification_type=NotificationType.STREAK_MILESTONE,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Streak milestone notification ({days}d) → {user.username}"
            ))
            return

        if kind == "perfect_day":
            notify(
                user,
                title="Perfect day",
                message="Every daily ritual touched.",
                notification_type=NotificationType.PERFECT_DAY,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Perfect day notification → {user.username}"
            ))
            return

        if kind == "birthday":
            from apps.chronicle.services import ChronicleService

            entry = ChronicleService.record_birthday(user)
            entry.metadata["gift_coins"] = opts["gift_coins"]
            entry.save(update_fields=["metadata"])
            notify(
                user,
                title=f"Happy birthday, {getattr(user, 'display_label', user.username)}!",
                message=(
                    "Your Yearbook has a new entry and "
                    f"{opts['gift_coins']} coins are in your treasury."
                ),
                notification_type=NotificationType.BIRTHDAY,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Birthday chronicle entry (id={entry.pk}, +{opts['gift_coins']} coins) "
                f"→ {user.username}"
            ))
            return

        raise CommandError(f"Unknown --type: {kind!r}")
