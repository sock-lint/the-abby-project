"""Re-base CreationDailyCounter on config.base_models.DailyCounterModel.

Schema-equivalent state migration: the abstract base declares the same
``user`` FK with ``related_name="+"`` (no reverse accessor); the original
``creation_daily_counters`` reverse name was unused outside the model
declaration. No DB columns or indexes change.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("creations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="creationdailycounter",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
