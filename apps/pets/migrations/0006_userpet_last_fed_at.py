# Generated for the 2026-04-23 pet-happiness feature.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0005_usermount_last_bred_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpet',
            name='last_fed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "When this pet was last fed. Drives the ``happiness_level`` "
                    "computation — see HAPPINESS_THRESHOLDS in apps/pets/services.py. "
                    "Gentle-nudge intent: stale pets dim visually, never take damage."
                ),
            ),
        ),
    ]
