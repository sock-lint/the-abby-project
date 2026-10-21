from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0037_progressionexperiment_challenge_gate_policies")]

    operations = [
        migrations.CreateModel(
            name="RPGContentRetirement",
            fields=[
                ("key", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
