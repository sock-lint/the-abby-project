"""Remember identifiable milestone completion history without paying it again."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_milestone_completion_receipts(apps, schema_editor):
    alias = schema_editor.connection.alias
    Milestone = apps.get_model("projects", "ProjectMilestone")
    Receipt = apps.get_model("projects", "MilestoneCompletionRewardReceipt")
    ActivityEvent = apps.get_model("activity", "ActivityEvent")
    completed_milestones = ActivityEvent.objects.using(alias).filter(
        event_type="milestone.complete",
        target_ct__app_label="projects", target_ct__model="projectmilestone",
    ).values("target_id")
    # A milestone-bonus ledger records only its project. It cannot identify
    # which milestone was paid, so it must not claim unrelated milestones.
    milestones = Milestone.objects.using(alias).filter(
        models.Q(is_completed=True) | models.Q(completed_at__isnull=False)
        | models.Q(pk__in=completed_milestones),
    ).exclude(completion_reward_receipt__isnull=False)
    batch = []
    for milestone in milestones.values("pk", "project__assigned_to_id").iterator(chunk_size=500):
        batch.append(Receipt(
            milestone_id=milestone["pk"], user_id=milestone["project__assigned_to_id"], historical=True,
        ))
        if len(batch) == 500:
            Receipt.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        Receipt.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0022_project_is_homework_plan"),
        ("activity", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MilestoneCompletionRewardReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("historical", models.BooleanField(default=False)),
                ("milestone", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="completion_reward_receipt", to="projects.projectmilestone",
                )),
                ("user", models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="milestone_completion_receipts", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"abstract": False},
        ),
        migrations.RunPython(backfill_milestone_completion_receipts, migrations.RunPython.noop),
    ]
