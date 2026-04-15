"""Adopt Habit and HabitLog from apps.rpg via state-only migration.

The physical tables (``rpg_habit``, ``rpg_habitlog``) were created by
``rpg/0002_habit_habitlog``. This migration only teaches Django's model
state that those tables now belong to ``apps.habits``. No SQL is emitted.

Paired with ``rpg/0008_move_habits_out`` which state-deletes the same
models from the ``rpg`` app. Together they form a no-op schema change.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("rpg", "0002_habit_habitlog"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Habit",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("name", models.CharField(max_length=100)),
                        ("icon", models.CharField(blank=True, max_length=10)),
                        ("habit_type", models.CharField(choices=[("positive", "Positive"), ("negative", "Negative"), ("both", "Both")], default="positive", max_length=8)),
                        ("coin_reward", models.PositiveIntegerField(default=1)),
                        ("xp_reward", models.PositiveIntegerField(default=5)),
                        ("strength", models.IntegerField(default=0)),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="created_habits", to=settings.AUTH_USER_MODEL)),
                        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="habits", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "rpg_habit",
                        "ordering": ["name"],
                    },
                ),
                migrations.CreateModel(
                    name="HabitLog",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("direction", models.SmallIntegerField()),
                        ("streak_at_time", models.IntegerField(default=0)),
                        ("habit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="habits.habit")),
                        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="habit_logs", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "rpg_habitlog",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
        ),
    ]
