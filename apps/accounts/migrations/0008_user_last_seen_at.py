from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_user_family_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="last_seen_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Stamped on each dashboard fetch — drives the since-last-visit summary.",
                null=True,
            ),
        ),
    ]
