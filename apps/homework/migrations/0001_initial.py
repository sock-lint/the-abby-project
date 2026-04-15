import decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0001_initial"),
        ("achievements", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomeworkAssignment",
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
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "subject",
                    models.CharField(
                        choices=[
                            ("math", "Math"),
                            ("reading", "Reading"),
                            ("writing", "Writing"),
                            ("science", "Science"),
                            ("social_studies", "Social Studies"),
                            ("art", "Art"),
                            ("music", "Music"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "effort_level",
                    models.IntegerField(
                        default=3,
                        help_text="1-5 scale. Drives reward scaling via HOMEWORK_EFFORT_MULTIPLIERS.",
                    ),
                ),
                ("due_date", models.DateField()),
                (
                    "reward_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        help_text="Base money reward before effort/timeliness scaling.",
                        max_digits=8,
                    ),
                ),
                (
                    "coin_reward",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Base coin reward before effort/timeliness scaling.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "notes",
                    models.TextField(
                        blank=True, help_text="Optional parent notes or context."
                    ),
                ),
                (
                    "assigned_to",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="homework_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_homework",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        help_text="Linked project for AI-planned long-form assignments.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="homework_assignments",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "ordering": ["due_date", "title"],
            },
        ),
        migrations.CreateModel(
            name="HomeworkTemplate",
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
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "subject",
                    models.CharField(
                        choices=[
                            ("math", "Math"),
                            ("reading", "Reading"),
                            ("writing", "Writing"),
                            ("science", "Science"),
                            ("social_studies", "Social Studies"),
                            ("art", "Art"),
                            ("music", "Music"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("effort_level", models.IntegerField(default=3)),
                (
                    "reward_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        max_digits=8,
                    ),
                ),
                ("coin_reward", models.PositiveIntegerField(default=0)),
                (
                    "skill_tags",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text='[{"skill_id": 1, "xp_amount": 15}, ...] for cloning.',
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="homework_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["title"],
            },
        ),
        migrations.CreateModel(
            name="HomeworkSubmission",
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
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending Approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=15,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="Optional child submission notes.",
                    ),
                ),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reward_amount_snapshot",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Final money reward (base × effort × timeliness), frozen at submission.",
                        max_digits=8,
                    ),
                ),
                (
                    "coin_reward_snapshot",
                    models.PositiveIntegerField(
                        help_text="Final coin reward (base × effort × timeliness), frozen at submission.",
                    ),
                ),
                (
                    "timeliness",
                    models.CharField(
                        choices=[
                            ("early", "Early"),
                            ("on_time", "On Time"),
                            ("late", "Late"),
                            ("beyond_cutoff", "Beyond Cutoff"),
                        ],
                        help_text="Computed at submission time by comparing submit date to due_date.",
                        max_length=15,
                    ),
                ),
                (
                    "timeliness_multiplier",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Frozen multiplier (e.g., 1.25 early, 1.0 on_time, 0.5 late, 0.0 beyond).",
                        max_digits=4,
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="homework.homeworkassignment",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="decided_homework_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="homework_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="homeworksubmission",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("status", "rejected")),
                fields=("assignment", "user"),
                name="unique_active_homework_submission",
            ),
        ),
        migrations.CreateModel(
            name="HomeworkSkillTag",
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
                (
                    "xp_amount",
                    models.PositiveIntegerField(
                        default=15,
                        help_text="XP awarded on approved completion.",
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_tags",
                        to="homework.homeworkassignment",
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="achievements.skill",
                    ),
                ),
            ],
            options={
                "unique_together": {("assignment", "skill")},
            },
        ),
        migrations.CreateModel(
            name="HomeworkProof",
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
                (
                    "image",
                    models.ImageField(upload_to="homework_proofs/%Y/%m/"),
                ),
                ("caption", models.CharField(blank=True, max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proofs",
                        to="homework.homeworksubmission",
                    ),
                ),
            ],
            options={
                "ordering": ["order"],
            },
        ),
    ]
