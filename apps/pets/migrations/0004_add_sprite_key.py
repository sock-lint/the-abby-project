from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0003_backfill_slugs'),
    ]

    operations = [
        migrations.AddField(
            model_name='petspecies',
            name='sprite_key',
            field=models.CharField(
                blank=True,
                help_text='Optional bundled pixel-art sprite slug; falls back to icon when empty.',
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name='potiontype',
            name='sprite_key',
            field=models.CharField(
                blank=True,
                help_text='Optional bundled pixel-art sprite slug for the potion icon.',
                max_length=64,
            ),
        ),
    ]
