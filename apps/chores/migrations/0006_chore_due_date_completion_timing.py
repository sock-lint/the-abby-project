from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chores", "0005_chore_family")]

    operations = [
        migrations.AddField(
            model_name="chore",
            name="due_date",
            field=models.DateField(
                blank=True, null=True,
                help_text="Optional household-local deadline for a one-time chore.",
            ),
        ),
        migrations.AddField(
            model_name="chorecompletion",
            name="timing_snapshot",
            field=models.JSONField(
                blank=True, default=None, editable=False, null=True,
                help_text="Server-owned schedule and submission dates; unknown for legacy rows.",
            ),
        ),
    ]
