"""Clear today's per-day counter rows so first-of-day gates re-arm.

Three concrete ``DailyCounterModel`` subclasses gate first-of-day
rewards in production: ``HomeworkDailyCounter``, ``CreationDailyCounter``,
``MovementDailyCounter``. The counter rows survive both soft- and
hard-delete of the parent rows (that's the anti-farm gate). This command
DELETES today's rows so the gates re-arm.

Examples::

    python manage.py reset_day_counters --user abby
    python manage.py reset_day_counters --user abby --kind homework
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import (
    DAY_COUNTER_KINDS, OperationError, reset_day_counters,
)


class Command(BaseCommand):
    help = "Delete today's daily-counter rows so first-of-day gates re-arm."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--kind",
            choices=list(DAY_COUNTER_KINDS) + ["all"],
            default="all",
            help="Which counter to clear (default 'all').",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        try:
            result = reset_day_counters(user, kind=opts["kind"])
        except OperationError as e:
            raise CommandError(str(e)) from e

        summary = ", ".join(f"{k}={v}" for k, v in result["deleted"].items())
        self.stdout.write(self.style.SUCCESS(
            f"Cleared today's counters for {user.username}: {summary}"
        ))
