from django.db import migrations, models


def complete_existing_budgets(apps, schema_editor):
    apps.get_model("rpg", "ProgressionExperiment").objects.using(schema_editor.connection.alias).update(
        candidate_expedition_budget={"daily_launches": None, "daily_items": None},
    )


class Migration(migrations.Migration):
    dependencies = [("rpg", "0035_progressionexperiment_candidate_policy")]

    operations = [
        migrations.AlterField(
            model_name="progressionexperiment", name="candidate_daily_coins",
            field=models.PositiveIntegerField(default=100, null=True),
        ),
        migrations.AlterField(
            model_name="progressionexperiment", name="candidate_policy",
            field=models.CharField(default="envelope", max_length=20, choices=[
                ("envelope", "Daily income envelope"), ("commitment100", "100-Coin commitment prototype"),
                ("expedition_limits", "Shared expedition limits"),
            ]),
        ),
        migrations.AddField(
            model_name="progressionexperiment", name="candidate_expedition_budget",
            field=models.JSONField(default=dict),
        ),
        migrations.RunPython(complete_existing_budgets, migrations.RunPython.noop),
    ]
