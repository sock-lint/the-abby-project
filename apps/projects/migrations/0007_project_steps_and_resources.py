import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0006_notification_redemption_requested"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectStep",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="steps",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ProjectResource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=200)),
                ("url", models.URLField(max_length=1000)),
                (
                    "resource_type",
                    models.CharField(
                        choices=[
                            ("link", "Link"),
                            ("video", "Video"),
                            ("doc", "Document"),
                            ("image", "Image"),
                        ],
                        default="link",
                        max_length=10,
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="resources",
                        to="projects.project",
                    ),
                ),
                (
                    "step",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="resources",
                        to="projects.projectstep",
                    ),
                ),
            ],
            options={
                "ordering": ["step_id", "order", "id"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="TemplateStep",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="steps",
                        to="projects.projecttemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="TemplateResource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=200)),
                ("url", models.URLField(max_length=1000)),
                (
                    "resource_type",
                    models.CharField(
                        choices=[
                            ("link", "Link"),
                            ("video", "Video"),
                            ("doc", "Document"),
                            ("image", "Image"),
                        ],
                        default="link",
                        max_length=10,
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "step",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="resources",
                        to="projects.templatestep",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="resources",
                        to="projects.projecttemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["step_id", "order", "id"],
            },
        ),
    ]
