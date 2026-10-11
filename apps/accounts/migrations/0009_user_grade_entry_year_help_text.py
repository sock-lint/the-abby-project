"""Record the current grade help text without changing stored user data."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_user_last_seen_at")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="user",
                    name="grade_entry_year",
                    field=models.PositiveIntegerField(
                        blank=True,
                        help_text="Calendar year of August they entered 9th grade (e.g. 2025).",
                        null=True,
                    ),
                ),
            ],
        ),
    ]
