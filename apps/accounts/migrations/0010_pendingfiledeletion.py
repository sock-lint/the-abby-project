import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_user_grade_entry_year_help_text")]

    operations = [
        migrations.CreateModel(
            name="PendingFileDeletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("storage_key", models.CharField(max_length=1000, unique=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("retry_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=32)),
            ],
            options={"ordering": ["retry_at", "pk"]},
        ),
    ]
