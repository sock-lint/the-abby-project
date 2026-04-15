"""Adopt SkillCategory from apps.projects via state-only migration.

Moves the full skill hierarchy — ``SkillCategory → Subject → Skill →
Badge`` — into one app. Previously ``SkillCategory`` lived in
``apps.projects`` while ``Subject``/``Skill`` lived in
``apps.achievements``, creating a bidirectional dependency.

The physical table (``projects_skillcategory``) was created by
``projects/0001_initial``. This migration teaches Django's model state
that the table now belongs to ``apps.achievements`` and re-targets
``Subject.category`` + ``Skill.category`` FKs to the new location. No
SQL is emitted — same db_table, same underlying columns.

Paired with ``projects/0015_move_skillcategory_out`` which state-deletes
the model from the projects app and re-targets ``Project.category`` +
``ProjectTemplate.category`` FKs.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0004_badge_award_coins_and_quest_completed_criteria"),
        ("projects", "0014_move_ingestion_out"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="SkillCategory",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=100, unique=True)),
                        ("icon", models.CharField(blank=True, max_length=50)),
                        ("color", models.CharField(default="#D97706", max_length=7)),
                        ("description", models.TextField(blank=True)),
                    ],
                    options={
                        "db_table": "projects_skillcategory",
                        "verbose_name_plural": "skill categories",
                        "ordering": ["name"],
                    },
                ),
                migrations.AlterField(
                    model_name="subject",
                    name="category",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subjects",
                        to="achievements.skillcategory",
                    ),
                ),
                migrations.AlterField(
                    model_name="skill",
                    name="category",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skills",
                        to="achievements.skillcategory",
                    ),
                ),
            ],
        ),
    ]
