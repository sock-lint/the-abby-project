"""Record field descriptions without changing gratitude or payout history."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wellbeing", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="dailywellbeingentry",
                    name="affirmation_slug",
                    field=models.CharField(
                        max_length=80,
                        help_text=(
                            "Slug of the affirmation pulled from content/wellbeing/affirmations.yaml. "
                            "Stored as a slug rather than the full text so editing the YAML "
                            "doesn't drift past entries — they re-resolve to the new copy."
                        ),
                    ),
                ),
                migrations.AlterField(
                    model_name="dailywellbeingentry",
                    name="gratitude_lines",
                    field=models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Up to 3 short gratitude entries the kid wrote. Empty list "
                            "until the first submit. Each entry is a plain string ≤200 "
                            "chars; validated by the service layer."
                        ),
                    ),
                ),
                migrations.AlterField(
                    model_name="dailywellbeingentry",
                    name="coin_paid_at",
                    field=models.DateTimeField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Timestamp of the first-of-day gratitude coin payout. Subsequent "
                            "edits on the same row don't repay the coin trickle — this field "
                            "is the idempotency key."
                        ),
                    ),
                ),
            ],
        ),
    ]
