"""State-only deletion of Habit/HabitLog — they now live in apps.habits.

Paired with ``habits/0001_initial`` which state-creates the same models
under the ``habits`` app label, preserving the underlying Postgres
tables (``rpg_habit``, ``rpg_habitlog``). Zero SQL is emitted.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0007_itemdefinition_sprite_key"),
        ("habits", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="HabitLog"),
                migrations.DeleteModel(name="Habit"),
            ],
        ),
    ]
