# Generated for the 2026-04-23 content review — caps consumable-driven pet
# growth (growth_surge, feast_platter) at CONSUMABLE_GROWTH_DAILY_CAP per
# pet per local day. Without the cap, a kid hoarding consumables could fully
# evolve a pet (0→100) in a single sitting; the design intent is real-world
# weeks of bonding.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0006_userpet_last_fed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpet',
            name='consumable_growth_today',
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Total growth this pet has received today from direct consumables "
                    "(growth_surge, feast_platter). Compared against "
                    "CONSUMABLE_GROWTH_DAILY_CAP in apps/pets/services.py. "
                    "Resets when consumable_growth_date != today."
                ),
            ),
        ),
        migrations.AddField(
            model_name='userpet',
            name='consumable_growth_date',
            field=models.DateField(
                blank=True,
                null=True,
                help_text=(
                    "Local date the consumable_growth_today counter applies to. "
                    "When stale, the counter is treated as 0 and reset on next apply."
                ),
            ),
        ),
    ]
