from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0020_sprite_authoring_inputs"),
    ]

    operations = [
        migrations.AddField(
            model_name="characterprofile",
            name="pending_companion_growth",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
