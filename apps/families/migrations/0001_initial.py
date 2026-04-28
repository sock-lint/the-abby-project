from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Family",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(db_index=True, max_length=140, unique=True)),
                ("timezone", models.CharField(default="America/Phoenix", max_length=64)),
                ("default_theme", models.CharField(
                    default="hyrule", max_length=20,
                    help_text="Cover applied for new members until they pick their own.")),
                ("primary_parent", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name="founded_families",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name_plural": "families",
                "ordering": ["name"],
            },
        ),
    ]
