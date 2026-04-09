from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0004_projectingestionjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="payment_kind",
            field=models.CharField(
                choices=[
                    ("required", "Required (allowance)"),
                    ("bounty", "Bounty (up for grabs)"),
                ],
                default="required",
                help_text=(
                    "Required projects are part of normal allowance; "
                    "bounty projects are up-for-grabs with a cash reward."
                ),
                max_length=10,
            ),
        ),
    ]
