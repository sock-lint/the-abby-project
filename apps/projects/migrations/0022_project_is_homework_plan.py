from django.db import migrations, models


def mark_existing_homework_plans(apps, schema_editor):
    database = schema_editor.connection.alias
    Assignment = apps.get_model("homework", "HomeworkAssignment")
    Project = apps.get_model("projects", "Project")
    linked = Assignment.objects.using(database).exclude(project_id=None).values("project_id")
    Project.objects.using(database).filter(pk__in=linked).update(is_homework_plan=True)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0021_backfill_project_completion_receipts"),
        ("homework", "0006_homeworkaisettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="project", name="is_homework_plan",
            field=models.BooleanField(default=False, editable=False, db_index=True),
        ),
        migrations.RunPython(mark_existing_homework_plans, migrations.RunPython.noop),
    ]
