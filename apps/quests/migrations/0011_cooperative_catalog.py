"""Route future shared starts correctly without changing accepted promises."""
from django.db import migrations, models


def identify_cooperative_templates(apps, schema_editor):
    QuestDefinition = apps.get_model("quests", "QuestDefinition")
    QuestDefinition.objects.using(schema_editor.connection.alias).filter(
        is_system=True, created_by__isnull=True, name="Family Co-op — Spring Cleaning",
    ).update(is_cooperative=True)


class Migration(migrations.Migration):
    dependencies = [("quests", "0010_catalog_supersession")]

    operations = [
        migrations.AddField(
            model_name="questdefinition", name="is_cooperative",
            field=models.BooleanField(
                default=False,
                help_text="A parent assigns this shared challenge to at least two children.",
            ),
        ),
        migrations.RunPython(identify_cooperative_templates, migrations.RunPython.noop),
    ]
