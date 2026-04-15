from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rpg', '0006_backfill_item_refs'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemdefinition',
            name='sprite_key',
            field=models.CharField(
                blank=True,
                help_text='Optional bundled pixel-art sprite slug; falls back to icon when empty.',
                max_length=64,
            ),
        ),
    ]
