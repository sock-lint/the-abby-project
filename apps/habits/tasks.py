import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def decay_habit_strength_task():
    """Decay strength of untapped habits toward 0 for all children."""
    from apps.habits.services import HabitService
    from apps.projects.models import User

    children = User.objects.filter(role="child")
    total_decayed = 0

    for child in children:
        total_decayed += HabitService.decay_all_habits(child)

    return f"Habit decay complete: {total_decayed} habits decayed across {children.count()} children."
