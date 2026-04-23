from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0019_alter_droptable_trigger_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="spriteasset",
            name="prompt",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="spriteasset",
            name="motion",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="spriteasset",
            name="style_hint",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="spriteasset",
            name="tile_size",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="spriteasset",
            name="reference_image_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
    ]
