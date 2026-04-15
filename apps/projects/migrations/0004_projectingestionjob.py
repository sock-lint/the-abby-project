import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0003_user_theme_projecttemplate_savingsgoal_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectIngestionJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("instructables", "Instructables"),
                            ("url", "Generic URL"),
                            ("pdf", "PDF Upload"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "source_url",
                    models.URLField(blank=True, max_length=1000, null=True),
                ),
                (
                    "source_file",
                    models.FileField(blank=True, null=True, upload_to="ingestion/"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                            ("discarded", "Discarded"),
                            ("committed", "Committed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("result_json", models.JSONField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ingestion_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingestion_jobs",
                        to="projects.project",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
