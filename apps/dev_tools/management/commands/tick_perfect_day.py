"""Run the daily Perfect Day evaluation synchronously.

Wraps ``apps.rpg.tasks.evaluate_perfect_day_task`` (normally Celery-Beat
at 23:55 local) so you can fire it on demand. The task itself iterates
across families and only awards children who genuinely qualify (active
today AND have ≥1 daily chore AND completed all of them) — this command
doesn't bypass that gate. To set up a perfect-day-eligible state for a
test child, complete their dailies first, then run this.

Examples::

    python manage.py tick_perfect_day
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.dev_tools.gate import assert_enabled


class Command(BaseCommand):
    help = "Run apps.rpg.tasks.evaluate_perfect_day_task synchronously."

    def handle(self, *args, **opts):
        assert_enabled()

        from apps.rpg.tasks import evaluate_perfect_day_task

        result = evaluate_perfect_day_task()
        self.stdout.write(self.style.SUCCESS(f"evaluate_perfect_day_task → {result}"))
