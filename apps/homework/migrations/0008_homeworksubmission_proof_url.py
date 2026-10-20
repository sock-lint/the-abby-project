from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("homework", "0007_homeworksubmission_timing_snapshot")]

    operations = [
        migrations.AddField(
            model_name="homeworksubmission",
            name="proof_url",
            field=models.URLField(blank=True, default="", max_length=2048),
        ),
    ]
