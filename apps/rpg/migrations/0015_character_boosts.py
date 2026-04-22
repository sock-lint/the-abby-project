"""Add CharacterProfile boost fields for new consumable effects.

- ``streak_freezes_used`` — lifetime counter exposed as the STREAK_FREEZE_USED
  badge criterion. Incremented in ``ConsumableService._apply_effect`` when a
  streak-freeze is consumed.
- ``xp_boost_expires_at`` / ``coin_boost_expires_at`` / ``drop_boost_expires_at``
  — timestamp gates for Scholar's Draught / Lucky Coin / Drop Charm
  consumables. ``None`` or past → no boost.
- ``pet_growth_boost_remaining`` — integer counter decremented as Growth Tonic
  feeds land. 0 → no boost.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0014_import_legacy_sprites"),
    ]

    operations = [
        migrations.AddField(
            model_name="characterprofile",
            name="streak_freezes_used",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Lifetime count of streak-freeze consumables used.",
            ),
        ),
        migrations.AddField(
            model_name="characterprofile",
            name="xp_boost_expires_at",
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="While in the future, Scholar's Draught multiplies XP gains.",
            ),
        ),
        migrations.AddField(
            model_name="characterprofile",
            name="coin_boost_expires_at",
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="While in the future, Lucky Coin multiplies coin drops.",
            ),
        ),
        migrations.AddField(
            model_name="characterprofile",
            name="drop_boost_expires_at",
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="While in the future, Drop Charm increases drop rates.",
            ),
        ),
        migrations.AddField(
            model_name="characterprofile",
            name="pet_growth_boost_remaining",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Number of pet feeds that still get Growth Tonic's 2x multiplier.",
            ),
        ),
    ]
