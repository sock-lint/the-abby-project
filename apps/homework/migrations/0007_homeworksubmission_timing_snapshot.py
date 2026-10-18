from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("homework", "0006_homeworkaisettings")]

    operations = [
        migrations.AddField(
            model_name="homeworksubmission", name="timing_snapshot",
            field=models.JSONField(blank=True, default=None, editable=False, null=True),
        ),
    ]
