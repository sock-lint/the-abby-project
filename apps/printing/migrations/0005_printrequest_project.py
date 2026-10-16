import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("printing", "0004_printbudget_minutes_per_coin_printrequest_coin_cost_and_more"),
        ("projects", "0018_projecttemplate_family"),
    ]

    operations = [
        migrations.AddField(
            model_name="printrequest",
            name="project",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="print_requests", to="projects.project",
            ),
        ),
    ]
