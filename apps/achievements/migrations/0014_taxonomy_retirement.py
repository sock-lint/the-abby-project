from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("achievements", "0013_alter_badge_criteria_type")]

    operations = [
        migrations.AddField(model_name=model, name="is_retired", field=models.BooleanField(default=False))
        for model in ("skillcategory", "subject", "skill")
    ]
