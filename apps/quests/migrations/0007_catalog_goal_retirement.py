"""Retire catalog templates without deleting saved goals or reward promises."""
import django.db.models.deletion
from django.db import migrations, models


def preserve_catalog_origin(apps, schema_editor):
    Goal = apps.get_model("quests", "ChallengeGoal")
    Occurrence = apps.get_model("quests", "ChallengeOccurrence")
    alias = schema_editor.connection.alias
    Goal.objects.using(alias).filter(catalog_definition__isnull=False).update(is_catalog=True)
    rows = Occurrence.objects.using(alias).filter(goal__is_catalog=True).select_related("goal__catalog_definition")
    for occurrence in rows.iterator(chunk_size=100):
        definition = occurrence.goal.catalog_definition
        occurrence.snapshot = {**occurrence.snapshot,
                               "catalog_name": definition.name, "catalog_type": definition.quest_type}
        occurrence.save(using=alias, update_fields=["snapshot"])


class Migration(migrations.Migration):
    dependencies = [("quests", "0006_parent_goal_request_identity")]

    operations = [
        migrations.AddField(
            model_name="challengegoal", name="is_catalog", field=models.BooleanField(default=False),
        ),
        migrations.RunPython(preserve_catalog_origin, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="challengegoal", name="catalog_definition",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    to="quests.questdefinition"),
        ),
    ]
