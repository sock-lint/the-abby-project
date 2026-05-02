import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def decay_habit_strength_task():
    """Decay strength of untapped habits toward 0 for all children."""
    from apps.families.queries import children_across_families
    from apps.habits.services import HabitService

    total_decayed = 0
    total_children = 0
    for _family, child in children_across_families():
        total_decayed += HabitService.decay_all_habits(child)
        total_children += 1

    return f"Habit decay complete: {total_decayed} habits decayed across {total_children} children."
