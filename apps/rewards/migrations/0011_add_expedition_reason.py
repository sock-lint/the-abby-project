# Adds the "expedition" CoinLedger reason for mount-expedition coin payouts.
# Mirrors 0010 — pure choices update, no data migration needed.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0010_add_daily_challenge_reason"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coinledger",
            name="reason",
            field=models.CharField(
                choices=[
                    ("hourly", "Hourly"),
                    ("project_bonus", "Project Bonus"),
                    ("bounty_bonus", "Bounty Bonus"),
                    ("milestone_bonus", "Milestone Bonus"),
                    ("badge_bonus", "Badge Bonus"),
                    ("redemption", "Redemption"),
                    ("refund", "Refund"),
                    ("adjustment", "Adjustment"),
                    ("chore_reward", "Chore Reward"),
                    ("exchange", "Exchange"),
                    ("daily_challenge", "Daily Challenge"),
                    ("expedition", "Expedition"),
                ],
                max_length=20,
            ),
        ),
    ]
