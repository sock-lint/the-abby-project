"""Start measurement for future enrollments without inventing historical views."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("quests", "0008_quest_reward_items_snapshot")]

    operations = [
        migrations.AddField(
            model_name="challengeenrollment", name="discovery_tracking_started_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True,
                help_text="Set only on new enrollment; null preserves unknown historical detail openings.",
            ),
        ),
        migrations.AddField(
            model_name="challengeoccurrence", name="first_details_opened_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
