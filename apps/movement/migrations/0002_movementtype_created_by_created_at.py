import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("movement", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="movementtype",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Null for seed data; set for user-authored types.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="authored_movement_types",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="movementtype",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
