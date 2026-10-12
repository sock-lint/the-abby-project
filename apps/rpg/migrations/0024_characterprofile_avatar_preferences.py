"""Persist appearance choices independently from earned cosmetics."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0023_characterprofile_growth_help_text_and_drop_triggers")]

    operations = [
        migrations.AddField(
            model_name="characterprofile",
            name="avatar_preferences",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Saved appearance choices for the owned Archer avatar; independent of rewards and cosmetic inventory.",
            ),
        ),
    ]
