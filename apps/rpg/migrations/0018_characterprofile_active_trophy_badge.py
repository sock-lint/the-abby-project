# Generated for the 2026-04-23 trophy-shelf feature.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('achievements', '0010_new_content_review_criteria'),
        ('rpg', '0017_characterprofile_consumable_effects_used'),
    ]

    operations = [
        migrations.AddField(
            model_name='characterprofile',
            name='active_trophy_badge',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='equipped_as_trophy',
                to='achievements.badge',
                help_text=(
                    "Optional hero badge the user has elected to display on their "
                    "profile and in notifications. Must be a badge they've earned; "
                    "enforcement lives in the trophy endpoint, not the schema, so the "
                    "FK can stay loose if badges are archived later."
                ),
            ),
        ),
    ]
