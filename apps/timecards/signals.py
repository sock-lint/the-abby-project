from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="timecards.TimeEntry")
def flag_long_entries(sender, instance, **kwargs):
    """Flag time entries longer than 4 hours for parent review."""
    if instance.duration_minutes > 240 and not instance.auto_clocked_out:
        pass  # Future: create notification for parent
