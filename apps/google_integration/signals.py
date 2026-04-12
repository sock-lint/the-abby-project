import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="projects.Project")
def sync_project_to_calendar(sender, instance, **kwargs):
    """Sync project due_date to Google Calendar when it changes."""
    if not instance.due_date or not instance.assigned_to_id:
        return

    # Only fire if due_date was in the update_fields (or this is a full save)
    update_fields = kwargs.get("update_fields")
    if update_fields and "due_date" not in update_fields:
        return

    from .models import GoogleAccount

    try:
        account = instance.assigned_to.google_account
        if not account.calendar_sync_enabled:
            return
    except GoogleAccount.DoesNotExist:
        return

    from .tasks import sync_project_due_date_task

    sync_project_due_date_task.delay(instance.id)


@receiver(post_save, sender="timecards.TimeEntry")
def sync_time_entry_to_calendar(sender, instance, **kwargs):
    """Sync completed time entries to Google Calendar."""
    if instance.status != "completed" or not instance.clock_out:
        return

    from .models import GoogleAccount

    try:
        account = instance.user.google_account
        if not account.calendar_sync_enabled:
            return
    except GoogleAccount.DoesNotExist:
        return

    from .tasks import sync_time_entry_task

    sync_time_entry_task.delay(instance.id)


@receiver(post_save, sender="chores.Chore")
def sync_chore_to_calendar(sender, instance, **kwargs):
    """Sync chore schedule to Google Calendar."""
    if not instance.is_active:
        return

    from .tasks import sync_chore_task

    sync_chore_task.delay(instance.id)
