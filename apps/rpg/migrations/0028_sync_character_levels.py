"""Refresh the historical level cache from saved XP without awarding anything.

The seven-tier curve is frozen here so future balance edits cannot reinterpret
this upgrade. A manually set legacy cache is replaced once; presentation-only
writes afterward continue to preserve it until a normal skill XP award syncs it.
"""
from django.db import migrations
from django.db.models import Sum


THRESHOLDS = {0: 0, 1: 100, 2: 300, 3: 600, 4: 1000, 5: 1500, 6: 2500}


def sync_character_levels(apps, schema_editor):
    Progress = apps.get_model("achievements", "SkillProgress")
    Profile = apps.get_model("rpg", "CharacterProfile")
    database = schema_editor.connection.alias
    totals = dict(
        Progress.objects.using(database).values("user_id").annotate(total=Sum("xp_points"))
        .values_list("user_id", "total")
    )
    for profile in Profile.objects.using(database).only("pk", "user_id", "level").iterator():
        total = totals.get(profile.user_id, 0)
        level = max((tier for tier, threshold in THRESHOLDS.items() if total >= threshold), default=0)
        if level != profile.level:
            Profile.objects.using(database).filter(pk=profile.pk).update(level=level)


class Migration(migrations.Migration):
    dependencies = [
        ("rpg", "0027_backfill_perfect_day_receipts"),
        ("achievements", "0001_initial"),
    ]

    operations = [migrations.RunPython(sync_character_levels, migrations.RunPython.noop)]
