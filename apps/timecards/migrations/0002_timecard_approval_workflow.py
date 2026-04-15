"""Migrate Timecard to inherit from ApprovalWorkflowModel.

Renames ``approved_by`` → ``decided_by`` and ``approved_at`` → ``decided_at``
so the model shares field semantics with ChoreCompletion, HomeworkSubmission,
RewardRedemption, and ExchangeRequest. Data in existing rows is preserved
via ``RenameField``; no backfill needed.

Also switches the ``decided_by`` FK ``related_name`` from the app-specific
``approved_timecards`` to ``+`` (ApprovalWorkflowModel's default, meaning no
reverse accessor). Verified unused via grep before removal.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("timecards", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="timecard",
            old_name="approved_at",
            new_name="decided_at",
        ),
        migrations.RenameField(
            model_name="timecard",
            old_name="approved_by",
            new_name="decided_by",
        ),
        migrations.AlterField(
            model_name="timecard",
            name="decided_by",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
