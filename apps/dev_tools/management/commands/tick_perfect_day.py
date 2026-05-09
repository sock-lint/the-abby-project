"""Run the daily Perfect Day evaluation synchronously.

Wraps ``apps.rpg.tasks.evaluate_perfect_day_task`` (normally Celery-Beat
at 23:55 local) so you can fire it on demand. The task only awards
children who genuinely qualify — this command doesn't bypass that gate.

Examples::

    python manage.py tick_perfect_day
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import tick_perfect_day


class Command(BaseCommand):
    help = "Run apps.rpg.tasks.evaluate_perfect_day_task synchronously."

    def handle(self, *args, **opts):
        assert_enabled()
        result = tick_perfect_day()
        self.stdout.write(self.style.SUCCESS(
            f"{result['task']} → {result['result']}"
        ))
