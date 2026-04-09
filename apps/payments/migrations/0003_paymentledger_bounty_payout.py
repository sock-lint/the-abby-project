from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentledger",
            name="entry_type",
            field=models.CharField(
                choices=[
                    ("hourly", "Hourly"),
                    ("project_bonus", "Project Bonus"),
                    ("bounty_payout", "Bounty Payout"),
                    ("milestone_bonus", "Milestone Bonus"),
                    ("materials_reimbursement", "Materials Reimbursement"),
                    ("payout", "Payout"),
                    ("adjustment", "Adjustment"),
                ],
                max_length=25,
            ),
        ),
    ]
