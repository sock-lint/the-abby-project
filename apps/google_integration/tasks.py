import logging
from datetime import date, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sync_project_due_date_task(project_id):
    """Push/update a project due date to Google Calendar."""
    from apps.projects.models import Project

    from .services import GoogleCalendarService

    try:
        project = Project.objects.select_related("assigned_to").get(pk=project_id)
    except Project.DoesNotExist:
        return f"Project {project_id} not found"

    GoogleCalendarService.sync_project_due_date(project)
    return f"Synced project {project_id} due date"


@shared_task
def sync_chore_task(chore_id):
    """Push/update chore recurring events to Google Calendar."""
    from apps.chores.models import Chore

    from .services import GoogleCalendarService

    try:
        chore = Chore.objects.get(pk=chore_id)
    except Chore.DoesNotExist:
        return f"Chore {chore_id} not found"

    GoogleCalendarService.sync_chore(chore)
    return f"Synced chore {chore_id}"


@shared_task
def sync_time_entry_task(time_entry_id):
    """Push a completed time entry as a calendar block."""
    from apps.timecards.models import TimeEntry

    from .services import GoogleCalendarService

    try:
        entry = TimeEntry.objects.select_related("user", "project").get(pk=time_entry_id)
    except TimeEntry.DoesNotExist:
        return f"TimeEntry {time_entry_id} not found"

    GoogleCalendarService.sync_time_entry(entry)
    return f"Synced time entry {time_entry_id}"


@shared_task
def remove_calendar_event_task(user_id, content_type, object_id):
    """Remove a Google Calendar event when the source is deleted."""
    from apps.projects.models import User

    from .services import GoogleCalendarService

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return f"User {user_id} not found"

    GoogleCalendarService.delete_event(user, content_type, object_id)
    return f"Removed calendar event {content_type}:{object_id} for user {user_id}"


@shared_task
def full_sync_task(user_id):
    """Manually triggered full resync of all events for a user."""
    from apps.projects.models import User

    from .services import GoogleCalendarService

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return f"User {user_id} not found"

    GoogleCalendarService.full_sync(user)
    return f"Full sync complete for user {user_id}"


@shared_task
def send_daily_reminders_task():
    """Daily reminders: project deadlines, chore reminders, parent approval queue.

    Runs at 7:00 AM via Celery Beat.
    """
    from apps.chores.models import Chore, ChoreCompletion
    from apps.chores.services import ChoreService
    from apps.projects.models import Project, User
    from apps.projects.notifications import notify
    from apps.rewards.models import ExchangeRequest, RewardRedemption
    from apps.timecards.models import Timecard

    today = date.today()
    tomorrow = today + timedelta(days=1)
    reminders_sent = 0

    # ── Project deadline reminders (for children) ────────────────────
    due_tomorrow = Project.objects.filter(
        due_date=tomorrow, status="in_progress"
    ).select_related("assigned_to")
    for project in due_tomorrow:
        if project.assigned_to_id:
            notify(
                project.assigned_to,
                f"{project.title} is due tomorrow!",
                message=f"Your project \"{project.title}\" is due {tomorrow.strftime('%A, %b %d')}.",
                notification_type="project_due_soon",
                link=f"/projects/{project.id}",
            )
            reminders_sent += 1

    due_today = Project.objects.filter(
        due_date=today, status="in_progress"
    ).select_related("assigned_to")
    for project in due_today:
        if project.assigned_to_id:
            notify(
                project.assigned_to,
                f"{project.title} is due today!",
                message=f"Your project \"{project.title}\" is due today.",
                notification_type="project_due_soon",
                link=f"/projects/{project.id}",
            )
            reminders_sent += 1

    # ── Chore reminders (for children) ───────────────────────────────
    children = User.objects.filter(role="child", is_active=True)
    active_chores = Chore.objects.filter(is_active=True)

    for child in children:
        for chore in active_chores:
            # Skip chores assigned to other children
            if chore.assigned_to_id and chore.assigned_to_id != child.id:
                continue

            # Skip alternating-week chores that aren't active this week
            if chore.week_schedule == "alternating":
                if not ChoreService.is_active_this_week(chore):
                    continue

            # Skip one-time chores that already have a completion
            if chore.recurrence == "one_time":
                if ChoreCompletion.objects.filter(chore=chore, user=child).exclude(
                    status="rejected"
                ).exists():
                    continue

            # Skip if already completed today
            already_done = ChoreCompletion.objects.filter(
                chore=chore, user=child, completed_date=today
            ).exclude(status="rejected").exists()
            if already_done:
                continue

            notify(
                child,
                f"Don't forget: {chore.title}",
                message=f"You have a chore to do today: {chore.title}",
                notification_type="chore_reminder",
                link="/chores",
            )
            reminders_sent += 1

    # ── Parent approval reminders ────────────────────────────────────
    pending_timecards = Timecard.objects.filter(status="pending").count()
    pending_chores = ChoreCompletion.objects.filter(status="pending").count()
    pending_redemptions = RewardRedemption.objects.filter(status="pending").count()
    pending_exchanges = ExchangeRequest.objects.filter(status="pending").count()
    total_pending = pending_timecards + pending_chores + pending_redemptions + pending_exchanges

    if total_pending > 0:
        parts = []
        if pending_timecards:
            parts.append(f"{pending_timecards} timecard{'s' if pending_timecards != 1 else ''}")
        if pending_chores:
            parts.append(f"{pending_chores} chore{'s' if pending_chores != 1 else ''}")
        if pending_redemptions:
            parts.append(f"{pending_redemptions} redemption{'s' if pending_redemptions != 1 else ''}")
        if pending_exchanges:
            parts.append(f"{pending_exchanges} exchange{'s' if pending_exchanges != 1 else ''}")

        message = f"You have {total_pending} item{'s' if total_pending != 1 else ''} awaiting approval: {', '.join(parts)}."

        parents = User.objects.filter(role="parent", is_active=True)
        for parent in parents:
            notify(
                parent,
                f"{total_pending} item{'s' if total_pending != 1 else ''} awaiting approval",
                message=message,
                notification_type="approval_reminder",
                link="/chores",
            )
            reminders_sent += 1

    return f"Daily reminders sent: {reminders_sent}"
