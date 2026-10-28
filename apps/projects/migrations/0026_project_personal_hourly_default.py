from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0025_savings_reward_milestones"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="hourly_rate_is_personal_default",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
