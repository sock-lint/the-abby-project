from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_backfill_default_family"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="family",
            field=models.ForeignKey(
                db_index=True,
                help_text="Household scope.",
                on_delete=models.deletion.CASCADE,
                related_name="members",
                to="families.family",
            ),
        ),
    ]
