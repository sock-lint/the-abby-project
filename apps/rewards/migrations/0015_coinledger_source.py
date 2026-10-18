from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0014_redemption_delivery_receipt")]

    operations = [
        migrations.AddField(
            model_name="coinledger", name="source",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=20,
                choices=[("", "Unattributed or other"), ("expedition", "Expedition Coins"),
                         ("expedition_salvage", "Expedition cosmetic salvage"), ("coin_pouch", "Coin pouch")],
                help_text="Typed future award attribution. Blank preserves unknown historical or other sources.",
            ),
        ),
    ]
