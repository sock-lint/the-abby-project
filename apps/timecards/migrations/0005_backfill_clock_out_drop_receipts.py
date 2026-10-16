from collections import defaultdict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import migrations


def preserve_completed_work_days(apps, schema_editor):
    """Do not reopen a historical day's opportunity or replay its rewards.

    Clock splits and former family timezone edits were not recorded as drop
    eligibility. Use recoverable completed work and the family's saved zone.
    """
    Entry = apps.get_model("timecards", "TimeEntry")
    Receipt = apps.get_model("timecards", "ClockOutDropReceipt")
    database = schema_editor.connection.alias
    totals = defaultdict(int)
    rows = Entry.objects.using(database).filter(
        status="completed", clock_out__isnull=False, duration_minutes__gt=0,
        project__is_homework_plan=False, project__homework_assignments__isnull=True,
    ).values_list("user_id", "user__family__timezone", "clock_out", "duration_minutes")
    for user_id, name, closed_at, minutes in rows.iterator(chunk_size=500):
        try:
            zone = ZoneInfo(name or "America/Phoenix")
        except (ValueError, ZoneInfoNotFoundError):
            zone = ZoneInfo("America/Phoenix")
        totals[(user_id, closed_at.astimezone(zone).date())] += minutes
    Receipt.objects.using(database).bulk_create([
        Receipt(user_id=user_id, occurred_on=day, historical=True)
        for (user_id, day), minutes in totals.items() if minutes >= 10
    ], ignore_conflicts=True, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("timecards", "0004_clock_out_daily_drop_receipt"),
        ("projects", "0022_project_is_homework_plan"),
    ]

    operations = [
        migrations.RunPython(preserve_completed_work_days, migrations.RunPython.noop),
    ]
