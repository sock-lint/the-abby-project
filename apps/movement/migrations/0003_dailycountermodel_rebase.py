"""Re-base MovementDailyCounter on config.base_models.DailyCounterModel and
tighten MovementType.created_at to NOT NULL.

The counter rebase is schema-equivalent — the abstract base declares the
same ``user`` FK with ``related_name="+"`` (no reverse accessor); the
original ``movement_daily_counters`` reverse name was unused outside the
model declaration.

The MovementType change backfills any null ``created_at`` rows to
``timezone.now()`` (only seed/legacy rows could have null) and then
tightens the column to NOT NULL by inheriting from
``CreatedAtModel``.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_movementtype_created_at(apps, schema_editor):
    MovementType = apps.get_model("movement", "MovementType")
    MovementType.objects.filter(created_at__isnull=True).update(
        created_at=timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("movement", "0002_movementtype_created_by_created_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="movementdailycounter",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            backfill_movementtype_created_at,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="movementtype",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
