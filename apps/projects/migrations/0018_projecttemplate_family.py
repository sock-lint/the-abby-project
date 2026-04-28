from django.db import migrations, models


def backfill_default_family(apps, schema_editor):
    Family = apps.get_model("families", "Family")
    Template = apps.get_model("projects", "ProjectTemplate")
    if not Template.objects.filter(family__isnull=True).exists():
        return
    family, _ = Family.objects.get_or_create(
        slug="default-family",
        defaults={"name": "Default Family"},
    )
    Template.objects.filter(family__isnull=True).update(family=family)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0017_savingsgoal_drop_current_amount"),
        ("families", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="projecttemplate",
            name="family",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.deletion.CASCADE,
                related_name="project_templates",
                to="families.family",
            ),
        ),
        migrations.RunPython(backfill_default_family, noop_reverse),
        migrations.AlterField(
            model_name="projecttemplate",
            name="family",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="project_templates",
                to="families.family",
            ),
        ),
        migrations.AlterField(
            model_name="projecttemplate",
            name="is_public",
            field=models.BooleanField(
                default=False,
                help_text="When True, visible to other families' Templates list.",
            ),
        ),
    ]
