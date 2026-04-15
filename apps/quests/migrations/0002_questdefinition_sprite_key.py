from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quests', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='questdefinition',
            name='sprite_key',
            field=models.CharField(
                blank=True,
                help_text='Optional bundled pixel-art sprite slug; falls back to icon when empty.',
                max_length=64,
            ),
        ),
    ]
