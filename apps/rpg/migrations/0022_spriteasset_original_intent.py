from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0021_characterprofile_pending_companion_growth"),
    ]

    operations = [
        migrations.AddField(
            model_name="spriteasset",
            name="original_intent",
            field=models.TextField(blank=True, default=""),
        ),
    ]
