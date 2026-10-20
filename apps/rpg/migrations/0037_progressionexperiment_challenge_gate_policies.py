from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0036_progressionexperiment_expedition_budget")]

    operations = [
        migrations.AlterField(
            model_name="progressionexperiment", name="candidate_policy",
            field=models.CharField(default="envelope", max_length=20, choices=[
                ("envelope", "Daily income envelope"), ("commitment100", "100-Coin commitment prototype"),
                ("expedition_limits", "Shared expedition limits"),
                ("milestone_gates", "Challenge milestone gates"),
                ("tenure_gates", "Challenge milestone and tenure gates"),
            ]),
        ),
    ]
