from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0018_projecttemplate_family"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialitem",
            name="is_on_hand",
            field=models.BooleanField(default=False),
        ),
    ]
