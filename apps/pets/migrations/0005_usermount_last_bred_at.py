# Generated for the 2026-04-23 pet-breeding mechanic.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0004_add_sprite_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermount',
            name='last_bred_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "When this mount last participated in a breeding. Used to enforce "
                    "the per-mount breeding cooldown — see MOUNT_BREEDING_COOLDOWN_DAYS "
                    "in apps/pets/services.py."
                ),
            ),
        ),
    ]
