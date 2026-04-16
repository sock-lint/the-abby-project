"""Drop money/coin fields from homework.

Homework no longer pays money or coins — rewards are XP, drops, streaks,
and quest progress only. ``PaymentLedger`` / ``CoinLedger`` rows from
prior approvals remain intact as historical records; we only drop the
mirror snapshot fields on HomeworkSubmission and the base reward fields
on HomeworkAssignment / HomeworkTemplate.

Also drops ``rewards_pending_review`` (no longer meaningful without
parent Adjust) and ``timeliness_multiplier`` (no longer used to scale a
snapshot).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("homework", "0003_homeworkassignment_rewards_pending_review"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="homeworkassignment",
            name="reward_amount",
        ),
        migrations.RemoveField(
            model_name="homeworkassignment",
            name="coin_reward",
        ),
        migrations.RemoveField(
            model_name="homeworkassignment",
            name="rewards_pending_review",
        ),
        migrations.RemoveField(
            model_name="homeworksubmission",
            name="reward_amount_snapshot",
        ),
        migrations.RemoveField(
            model_name="homeworksubmission",
            name="coin_reward_snapshot",
        ),
        migrations.RemoveField(
            model_name="homeworksubmission",
            name="timeliness_multiplier",
        ),
        migrations.RemoveField(
            model_name="homeworktemplate",
            name="reward_amount",
        ),
        migrations.RemoveField(
            model_name="homeworktemplate",
            name="coin_reward",
        ),
        migrations.AlterField(
            model_name="homeworkassignment",
            name="effort_level",
            field=models.IntegerField(
                default=3,
                help_text="1-5 scale. Weights XP distribution across skill tags.",
            ),
        ),
    ]
