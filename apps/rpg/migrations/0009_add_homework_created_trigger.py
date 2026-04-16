"""Register ``homework_created`` as a DropTable trigger type."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0008_move_habits_to_habits_app"),
    ]

    operations = [
        migrations.AlterField(
            model_name="droptable",
            name="trigger_type",
            field=models.CharField(
                choices=[
                    ("clock_out", "Clock Out"),
                    ("chore_complete", "Chore Complete"),
                    ("homework_complete", "Homework Complete"),
                    ("homework_created", "Homework Created"),
                    ("milestone_complete", "Milestone Complete"),
                    ("badge_earned", "Badge Earned"),
                    ("quest_complete", "Quest Complete"),
                    ("perfect_day", "Perfect Day"),
                    ("habit_log", "Habit Log"),
                ],
                max_length=30,
            ),
        ),
    ]
