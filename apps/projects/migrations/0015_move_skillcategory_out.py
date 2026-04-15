"""State-only removal of SkillCategory — now in apps.achievements.

Paired with ``achievements/0005_receive_skillcategory`` which state-
creates the model under the achievements app label. This migration
drops the projects-app state entry and re-targets the two
projects-side FK fields (``Project.category``,
``ProjectTemplate.category``) to the new location. No SQL is emitted.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0014_move_ingestion_out"),
        ("achievements", "0005_receive_skillcategory"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="project",
                    name="category",
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="projects",
                        to="achievements.skillcategory",
                    ),
                ),
                migrations.AlterField(
                    model_name="projecttemplate",
                    name="category",
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="templates",
                        to="achievements.skillcategory",
                    ),
                ),
                migrations.DeleteModel(name="SkillCategory"),
            ],
        ),
    ]
