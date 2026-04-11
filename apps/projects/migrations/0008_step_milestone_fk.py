import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0007_project_steps_and_resources"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectstep",
            name="milestone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="steps",
                to="projects.projectmilestone",
            ),
        ),
        migrations.AddField(
            model_name="templatestep",
            name="milestone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="steps",
                to="projects.templatemilestone",
            ),
        ),
    ]
