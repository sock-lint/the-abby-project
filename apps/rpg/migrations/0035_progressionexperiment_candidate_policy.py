from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0034_progressionobservation")]

    operations = [
        migrations.AddField(
            model_name="progressionexperiment",
            name="candidate_policy",
            field=models.CharField(
                choices=[("envelope", "Daily income envelope"),
                         ("commitment100", "100-Coin commitment prototype")],
                default="envelope", max_length=20,
            ),
        ),
    ]
