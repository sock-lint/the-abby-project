from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0029_alter_droptable_trigger_type")]
    operations = [migrations.AddField(
        model_name="droplog", name="salvage_coins",
        field=models.PositiveIntegerField(null=True, blank=True, editable=False,
            help_text="Exact Coins awarded for this drop; null means an older receipt did not record the amount."),
    )]
