from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0005_project_payment_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("timecard_ready", "Timecard Ready"),
                    ("timecard_approved", "Timecard Approved"),
                    ("badge_earned", "Badge Earned"),
                    ("project_approved", "Project Approved"),
                    ("project_changes", "Changes Requested"),
                    ("payout_recorded", "Payout Recorded"),
                    ("skill_unlocked", "Skill Unlocked"),
                    ("milestone_completed", "Milestone Completed"),
                    ("redemption_requested", "Redemption Requested"),
                ],
                max_length=25,
            ),
        ),
    ]
