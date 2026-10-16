from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("habits", "0005_habit_pending_parent_review")]

    operations = [
        migrations.AddField(
            model_name="habit",
            name="last_decay_date",
            field=models.DateField(
                blank=True, null=True,
                help_text="Last completed local day evaluated for strength decay.",
            ),
        ),
    ]
