"""Drop ``Habit.coin_reward`` and add ``Habit.max_taps_per_day``.

Habits no longer award coins — coin earning is reserved for chores,
project/milestone completion, and badge drops. The new
``max_taps_per_day`` field lets parents cap per-day taps per habit
(e.g. "Brush teeth" = 2/day). Existing habits default to ``1/day``;
parents bump up where the habit warrants it.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="habit",
            name="coin_reward",
        ),
        migrations.AddField(
            model_name="habit",
            name="max_taps_per_day",
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
