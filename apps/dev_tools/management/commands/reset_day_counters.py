"""Clear today's per-day counter rows so first-of-day gates re-arm.

Three concrete ``DailyCounterModel`` subclasses gate first-of-day
rewards in production:

  * ``HomeworkDailyCounter``  — first homework create per day fires
                                ``GameLoopService.on_task_completed``
  * ``CreationDailyCounter``  — first 2 creations per day earn XP
  * ``MovementDailyCounter``  — first session per day fires the loop

The counter rows survive both soft- and hard-delete of the parent rows
(that's the anti-farm gate). This command DELETES today's rows so the
gates re-arm. Useful when manually testing the same first-of-day surface
multiple times in one day.

Examples::

    python manage.py reset_day_counters --user abby
    python manage.py reset_day_counters --user abby --kind homework
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled


_KINDS = {
    "homework": ("apps.homework.models", "HomeworkDailyCounter"),
    "creation": ("apps.creations.models", "CreationDailyCounter"),
    "movement": ("apps.movement.models", "MovementDailyCounter"),
}


class Command(BaseCommand):
    help = "Delete today's daily-counter rows so first-of-day gates re-arm."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--kind",
            choices=list(_KINDS) + ["all"],
            default="all",
            help="Which counter to clear (default 'all').",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        today = timezone.localdate()
        targets = _KINDS if opts["kind"] == "all" else {opts["kind"]: _KINDS[opts["kind"]]}

        deleted = {}
        for kind, (module_path, cls_name) in targets.items():
            from importlib import import_module
            cls = getattr(import_module(module_path), cls_name)
            qs = cls.objects.filter(user=user, occurred_on=today)
            count = qs.count()
            qs.delete()
            deleted[kind] = count

        summary = ", ".join(f"{k}={v}" for k, v in deleted.items())
        self.stdout.write(self.style.SUCCESS(
            f"Cleared today's counters for {user.username}: {summary}"
        ))
