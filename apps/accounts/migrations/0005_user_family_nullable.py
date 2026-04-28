from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_lorebook_flags"),
        ("families", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="family",
            field=models.ForeignKey(
                blank=True, null=True,
                db_index=True,
                help_text=(
                    "Household scope. Nullable during migration backfill; "
                    "tightened to non-null in a later migration."
                ),
                on_delete=models.deletion.CASCADE,
                related_name="members",
                to="families.family",
            ),
        ),
    ]
