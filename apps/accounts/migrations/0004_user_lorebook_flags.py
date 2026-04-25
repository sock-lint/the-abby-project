from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_date_of_birth_user_grade_entry_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="lorebook_flags",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
