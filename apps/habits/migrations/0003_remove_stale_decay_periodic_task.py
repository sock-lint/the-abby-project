"""Drop stale ``PeriodicTask`` rows pointing at the old task path.

``decay_habit_strength_task`` was moved from ``apps.rpg.tasks`` to
``apps.habits.tasks`` when habits became their own app. Production uses
``django_celery_beat.DatabaseScheduler``, which persists the beat
schedule in ``django_celery_beat.PeriodicTask``. The row keyed by
``habit-decay`` survived the code move and kept dispatching messages
with the old task name, which the worker rejects with
``KeyError: 'apps.rpg.tasks.decay_habit_strength_task'`` every night at
00:05 local.

Deleting the stale row is safe: ``DatabaseScheduler.setup_schedule()``
re-syncs ``CELERY_BEAT_SCHEDULE`` on the next beat startup and recreates
the entry with the correct task path.
"""

from django.db import migrations


OLD_TASK_PATH = "apps.rpg.tasks.decay_habit_strength_task"


def remove_stale_periodic_tasks(apps, schema_editor):
    try:
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return
    PeriodicTask.objects.filter(task=OLD_TASK_PATH).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0002_habit_taps_per_day"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            remove_stale_periodic_tasks,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
