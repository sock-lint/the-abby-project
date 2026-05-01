"""Add HomeworkDailyCounter for the homework_created anti-farm gate.

Replaces the prior ``HomeworkAssignment.objects.filter(created_at__date=…)``
query in ``HomeworkService.create_assignment``. The counter pattern is
race-safe (read-modify-write under ``select_for_update``) and survives
both soft-delete (``is_active=False``) and hard-delete of the assignment
row, so a parent-cooperated create→delete→create cycle within the same
local day cannot re-arm streak / drop / quest credit.

Mirrors ``creations.CreationDailyCounter`` and
``movement.MovementDailyCounter``; all three concrete models now inherit
from ``config.base_models.DailyCounterModel``.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("homework", "0004_drop_currency_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HomeworkDailyCounter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("occurred_on", models.DateField()),
                ("count", models.PositiveIntegerField(default=0)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["user", "occurred_on"],
                        name="homework_h_user_id_dc01a8_idx",
                    )
                ],
                "unique_together": {("user", "occurred_on")},
            },
        ),
    ]
