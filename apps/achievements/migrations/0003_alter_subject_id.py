from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0002_subject"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subject",
            name="id",
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
    ]
