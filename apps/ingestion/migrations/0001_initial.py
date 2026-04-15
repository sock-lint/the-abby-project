"""Adopt ProjectIngestionJob from apps.projects via state-only migration.

The physical table (``projects_projectingestionjob``) was created by
``projects/0004_projectingestionjob``. This migration teaches Django's
model state that the table now belongs to ``apps.ingestion``. No SQL
is emitted.

Paired with ``projects/0014_move_ingestion_out`` which state-deletes
the same model from the ``projects`` app.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0004_projectingestionjob"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ProjectIngestionJob",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("source_type", models.CharField(
                            choices=[
                                ("instructables", "Instructables"),
                                ("url", "Generic URL"),
                                ("pdf", "PDF Upload"),
                            ],
                            max_length=20,
                        )),
                        ("source_url", models.URLField(blank=True, max_length=1000, null=True)),
                        ("source_file", models.FileField(blank=True, null=True, upload_to="ingestion/")),
                        ("status", models.CharField(
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
                        )),
                        ("result_json", models.JSONField(blank=True, null=True)),
                        ("error", models.TextField(blank=True)),
                        ("created_by", models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="ingestion_jobs",
                            to=settings.AUTH_USER_MODEL,
                        )),
                        ("project", models.ForeignKey(
                            blank=True,
                            null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name="ingestion_jobs",
                            to="projects.project",
                        )),
                    ],
                    options={
                        "db_table": "projects_projectingestionjob",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
        ),
    ]
