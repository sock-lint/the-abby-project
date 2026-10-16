"""Protect already-paid days without changing earned counters or balances.

Old events did not record their calendar date. Their producer used the configured
America/Phoenix day, regardless of the family's zone; freeze that actual legacy
policy here. New events carry an explicit date in context.
"""
from datetime import date
from zoneinfo import ZoneInfo

from django.db import migrations


def backfill_perfect_day_receipts(apps, schema_editor):
    Event = apps.get_model("activity", "ActivityEvent")
    Receipt = apps.get_model("rpg", "PerfectDayReceipt")
    database = schema_editor.connection.alias
    events = Event.objects.using(database).filter(
        category="system", event_type="system.perfect_day", subject__isnull=False,
    )
    for event in events.iterator():
        context = event.context if isinstance(event.context, dict) else {}
        extras = context.get("extras", {})
        recorded_day = extras.get("day") if isinstance(extras, dict) else None
        try:
            day = date.fromisoformat(recorded_day)
        except (TypeError, ValueError):
            day = event.occurred_at.astimezone(ZoneInfo("America/Phoenix")).date()
        Receipt.objects.using(database).get_or_create(
            user_id=event.subject_id, day=day, defaults={"historical": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("rpg", "0026_perfectdayreceipt"),
        ("activity", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill_perfect_day_receipts, migrations.RunPython.noop)]
