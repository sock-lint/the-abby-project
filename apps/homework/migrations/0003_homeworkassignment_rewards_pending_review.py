from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('homework', '0002_alter_homeworksubmission_decided_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='homeworkassignment',
            name='rewards_pending_review',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True when a child created this assignment without setting "
                    "effort/reward/coins. Cleared when AI or a parent (via Adjust) "
                    "fills in the values at submission time."
                ),
            ),
        ),
    ]
