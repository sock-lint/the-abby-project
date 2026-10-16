"""Preserve earlier completion history without issuing or reversing rewards."""
from django.db import migrations, models


def backfill_completion_receipts(apps, schema_editor):
    alias = schema_editor.connection.alias
    Project = apps.get_model("projects", "Project")
    Receipt = apps.get_model("projects", "ProjectCompletionRewardReceipt")
    PaymentLedger = apps.get_model("payments", "PaymentLedger")
    ActivityEvent = apps.get_model("activity", "ActivityEvent")

    paid_projects = PaymentLedger.objects.using(alias).filter(
        entry_type__in=["project_bonus", "bounty_payout"], project_id__isnull=False,
    ).values("project_id")
    completed_projects = ActivityEvent.objects.using(alias).filter(
        event_type="project.complete", target_ct__app_label="projects", target_ct__model="project",
    ).values("target_id")
    projects = Project.objects.using(alias).filter(
        models.Q(status="completed") | models.Q(completed_at__isnull=False)
        | models.Q(pk__in=paid_projects) | models.Q(pk__in=completed_projects),
    ).exclude(completion_reward_receipt__isnull=False)

    batch = []
    for project in projects.only("id", "assigned_to_id").iterator(chunk_size=500):
        batch.append(Receipt(project_id=project.pk, user_id=project.assigned_to_id, historical=True))
        if len(batch) == 500:
            Receipt.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        Receipt.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0020_projectcompletionrewardreceipt"),
        ("payments", "0007_greenlighttransfer_greenlightstatementtransfer_and_more"),
        ("activity", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_completion_receipts, migrations.RunPython.noop),
    ]
