import csv
import io

from .models import Timecard, TimeEntry


def export_timecards_csv(user, is_parent=False):
    """Export timecards as CSV content."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Week Start", "Week End", "User", "Total Hours",
        "Hourly Earnings", "Bonus Earnings", "Total Earnings", "Status",
    ])

    qs = Timecard.objects.all() if is_parent else Timecard.objects.filter(user=user)
    for tc in qs.select_related("user"):
        writer.writerow([
            tc.week_start, tc.week_end,
            tc.user.display_label,
            tc.total_hours, tc.hourly_earnings,
            tc.bonus_earnings, tc.total_earnings, tc.status,
        ])

    return output.getvalue()


def export_time_entries_csv(user, is_parent=False):
    """Export individual time entries as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "User", "Project", "Clock In", "Clock Out",
        "Duration (min)", "Notes", "Status",
    ])

    qs = TimeEntry.objects.filter(status="completed")
    if not is_parent:
        qs = qs.filter(user=user)

    for entry in qs.select_related("user", "project"):
        writer.writerow([
            entry.clock_in.date(),
            entry.user.display_label,
            entry.project.title,
            entry.clock_in.strftime("%H:%M"),
            entry.clock_out.strftime("%H:%M") if entry.clock_out else "",
            entry.duration_minutes,
            entry.notes,
            entry.status,
        ])

    return output.getvalue()
